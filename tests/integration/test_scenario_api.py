import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.scenario_routes import options_router, router
from repositories.scenario_repository import ScenarioRepository
from schemas.scenario import StepType
from services.scenario_service import ScenarioServiceError
from utils.chat_history_handler import AsyncConversationStore


@pytest.mark.asyncio
async def test_create_save_and_fetch_scenario(tmp_path) -> None:
    store = await AsyncConversationStore.create(str(tmp_path / "api.db"))
    app = FastAPI()
    app.state.sqlite_conn = store
    app.include_router(router)
    app.include_router(options_router)

    @app.exception_handler(ScenarioServiceError)
    async def handle_error(request: Request, exc: ScenarioServiceError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            options = await client.get("/api/scenario-options")
            assert options.status_code == 200
            assert {"terrain_types", "scenario_scales", "weapon_categories", "echelons"} <= options.json().keys()
            assert "task_types" not in options.json()
            assert options.json()["terrain_types"][0]["builtin"] is True

            created = await client.post("/api/scenarios", json={"title": "API scenario"})
            assert created.status_code == 201
            scenario_id = created.json()["id"]

            saved = await client.put(
                f"/api/scenarios/{scenario_id}/steps/background/input",
                json={
                    "input": {
                        "location_mode": "terrain_template",
                        "terrain_types": ["mountain"],
                        "season": "summer",
                        "operation_context": "exercise",
                    }
                },
            )
            assert saved.status_code == 200
            assert saved.json()["steps"][0]["status"] == "draft"
            assert [step["status"] for step in saved.json()["steps"][1:]] == [
                "empty",
                "empty",
                "empty",
            ]

            fetched = await client.get(f"/api/scenarios/{scenario_id}")
            assert fetched.status_code == 200
            assert fetched.json()["steps"][0]["input"]["terrain_types"] == ["mountain"]

            blocked = await client.post(
                f"/api/scenarios/{scenario_id}/steps/background/confirm",
                json={"version": 1},
            )
            assert blocked.status_code == 409
            assert blocked.json()["error"]["code"] == "VERSION_CONFLICT"

            repository = ScenarioRepository(store.conn)
            background_version = await repository.add_version(
                scenario_id, StepType.BACKGROUND, "background output", {}, []
            )
            confirmed = await client.post(
                f"/api/scenarios/{scenario_id}/steps/background/confirm",
                json={"version": background_version},
            )
            assert confirmed.status_code == 200
            assert confirmed.json()["steps"][0]["status"] == "confirmed"

            changed = await client.put(
                f"/api/scenarios/{scenario_id}/steps/background/input",
                json={
                    "input": {
                        "location_mode": "terrain_template",
                        "terrain_types": ["mountain"],
                        "season": "winter",
                        "operation_context": "exercise",
                    }
                },
            )
            assert [step["status"] for step in changed.json()["steps"]] == [
                "draft",
                "stale",
                "stale",
                "stale",
            ]
    finally:
        await store.close()
