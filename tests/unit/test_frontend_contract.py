from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient
import pytest


ROOT = Path(__file__).parents[2]


@pytest.mark.asyncio
async def test_scenario_static_page_exposes_workflow_assets() -> None:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=ROOT / "src" / "static", html=True), name="static")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        page = await client.get("/static/new_new.html")
        stylesheet = await client.get("/static/scenario.css")
        script = await client.get("/static/scenario.js")

    assert page.status_code == 200
    assert 'id="stepper"' in page.text
    assert 'id="knowledge-modal"' in page.text
    assert 'id="knowledge-delete-modal"' in page.text
    assert "/static/scenario.css?v=5" in page.text
    assert "/static/scenario.js?v=5" in page.text
    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert "localStorage" not in script.text
    assert "/api/scenario-options" in script.text
    assert "weather_mode" in script.text
