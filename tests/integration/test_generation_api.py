import json
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.scenario_routes import router
from services.scenario_service import ScenarioServiceError
from utils.chat_history_handler import AsyncConversationStore


class ApiFakeGenerator:
    async def stream(self, *args, **kwargs) -> AsyncIterator[str]:
        yield "first "
        yield "draft"


class ApiFailingGenerator:
    async def stream(self, *args, **kwargs) -> AsyncIterator[str]:
        raise RuntimeError("external model failed")
        yield "unreachable"


@pytest.mark.asyncio
async def test_generation_endpoint_streams_ndjson_and_is_idempotent(tmp_path) -> None:
    store = await AsyncConversationStore.create(str(tmp_path / "generation-api.db"))
    app = FastAPI()
    app.state.sqlite_conn = store
    app.state.scenario_generator = ApiFakeGenerator()
    app.include_router(router)

    @app.exception_handler(ScenarioServiceError)
    async def handle_error(request: Request, exc: ScenarioServiceError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/api/scenarios", json={"title": "Streaming"})
            scenario_id = created.json()["id"]
            blocked = await client.post(
                f"/api/scenarios/{scenario_id}/steps/formation/generate",
                json={"mode": "generate", "request_id": "blocked-formation"},
            )
            assert blocked.status_code == 409
            assert blocked.json()["error"]["code"] == "PREREQUISITE_NOT_CONFIRMED"
            await client.put(
                f"/api/scenarios/{scenario_id}/steps/background/input",
                json={
                    "input": {
                        "location_mode": "exact_location",
                        "location": {
                            "place_id": "mock:beijing",
                            "display_name": "北京市，中国",
                            "country": "中国",
                            "admin1": "北京市",
                            "latitude": 39.9042,
                            "longitude": 116.4074,
                            "bbox": [39.4, 41.1, 115.4, 117.5],
                            "source": "mock",
                        },
                        "season": "summer",
                        "operation_context": "exercise",
                    }
                },
            )
            payload = {"mode": "generate", "request_id": "api-request"}
            response = await client.post(
                f"/api/scenarios/{scenario_id}/steps/background/generate",
                json=payload,
            )
            events = [json.loads(line) for line in response.text.splitlines()]

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("application/x-ndjson")
            assert [event["type"] for event in events] == [
                "progress",
                "progress",
                "content",
                "content",
                "done",
            ]
            assert events[-1]["version"] == 1

            replay = await client.post(
                f"/api/scenarios/{scenario_id}/steps/background/generate",
                json=payload,
            )
            assert json.loads(replay.text)["replayed"] is True

            versions = await client.get(
                f"/api/scenarios/{scenario_id}/steps/background/versions"
            )
            assert versions.json()[0]["output_text"] == "first draft"
            assert versions.json()[0]["input_snapshot"]["season"] == "summer"

            app.state.scenario_generator = ApiFailingGenerator()
            failed = await client.post(
                f"/api/scenarios/{scenario_id}/steps/background/generate",
                json={"mode": "regenerate", "request_id": "failed-api-request"},
            )
            failure_events = [json.loads(line) for line in failed.text.splitlines()]
            failure_event = failure_events[-1]
            assert failed.status_code == 200
            assert failure_event["type"] == "error"
            assert failure_event["code"] == "GENERATION_FAILED"

            after_failure = await client.get(
                f"/api/scenarios/{scenario_id}/steps/background/versions"
            )
            assert len(after_failure.json()) == 1
            scenario = await client.get(f"/api/scenarios/{scenario_id}")
            assert scenario.json()["steps"][0]["current_output"] == "first draft"
    finally:
        await store.close()
