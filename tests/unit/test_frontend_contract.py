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
    assert 'id="knowledge-level"' in page.text
    assert 'id="knowledge-source"' in page.text
    assert "/static/scenario.css?v=15" in page.text
    assert "/static/scenario.js?v=17" in page.text
    assert "marked-12.0.2.min.js" in page.text
    assert "dompurify-3.1.6.min.js" in page.text
    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert "localStorage" not in script.text
    assert "/api/scenario-options" in script.text
    assert "/api/locations/search" in script.text
    assert "setTimeout(() => searchLocations(query, requestId), 500)" in script.text
    assert "location.address" in script.text
    assert "weather_mode" in script.text
    assert "/api/knowledge/${encodeURIComponent(id)}/approve" in script.text
    assert "knowledge-card-review" in script.text
    assert "entry.source" in script.text
    assert "entry.level" in script.text
    assert "weapon_categories" in script.text
    assert "weaponSelectionSummary" in script.text
    assert "confirmWeaponSelection" in script.text
    assert 'id="weapon-modal"' in page.text
    assert "campaign_tactics" in script.text
    assert "tactical_tactics" in script.text
    assert "添加自定义战役战法" not in script.text
    assert "添加自定义战术战法" not in script.text
    assert "`添加红方自定义${label}`" in script.text
    assert "`添加蓝方自定义${label}`" in script.text
    for side in ("red", "blue"):
        assert f"{side}_campaign_tactics_custom" in script.text
        assert f"{side}_tactical_tactics_custom" in script.text
    assert "recommendation-content" in script.text
    assert "item.content" in script.text
    assert "recommendation_snapshots" in script.text
    assert "selectedRecommendationSnapshots" in script.text
    assert "data-recommendation-id" in script.text
    assert ".recommendation-list{display:grid" in stylesheet.text
    assert ".side-tactic-custom-grid{grid-column:1/-1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" in stylesheet.text
    assert ".recommendation-list,.side-tactic-custom-grid{grid-template-columns:1fr}" in stylesheet.text
    assert "function renderMarkdown" in script.text
    assert "DOMPurify.sanitize" in script.text
    assert "output.scrollTop = output.scrollHeight" in script.text
    assert "function scrollWorkspaceToTop()" in script.text
    assert "scrollWorkspaceToTop();" in script.text
    assert "loading-dots" in stylesheet.text
    assert "height:calc(100vh - var(--topbar-height))" in stylesheet.text
    for removed in ("name=\"level\"", "name=\"action_types\"", "name=\"task_types\"", "name=\"phase_template\""):
        assert removed not in script.text
    assert "Generating " not in script.text
    assert "Preparing " not in script.text
