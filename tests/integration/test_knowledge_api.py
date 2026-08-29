from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from api import knowledge_routes


class Store:
    def __init__(self):
        self.entry = None
        self.verified = False

    def get_texts_by_category(self, category):
        return [] if self.entry is None else [{"k_id": "entry-1", "kb_id": category, **self.entry}]

    def find_by_content_hash(self, value):
        return {"k_id": "entry-1", "verified": self.verified} if self.entry else None

    def add_text(self, content, category, metadata):
        self.entry = {"content": content, "category": category, **metadata}
        return ["entry-1"]

    def set_verified(self, knowledge_id, verified):
        if not self.entry:
            return False
        self.verified = verified
        self.entry["verified"] = verified
        return True

    async def adelete_text_by_id(self, knowledge_id):
        if self.entry is None:
            return False
        self.entry = None
        return True


@pytest.mark.asyncio
async def test_knowledge_base_names_use_battle_method_wording() -> None:
    app = FastAPI()
    app.include_router(knowledge_routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/get_knowledge_bases")

    names = {item["kb_id"]: item["name"] for item in response.json()}
    assert names["tactics_campaign"] == "战役级战法知识库"
    assert names["tactics_tactical"] == "战术级战法知识库"


@pytest.mark.asyncio
async def test_knowledge_creation_review_and_duplicate_contract(monkeypatch) -> None:
    store = Store()
    monkeypatch.setattr(knowledge_routes, "_knowledge_store", store)
    app = FastAPI()
    app.include_router(knowledge_routes.router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/add_knowledge",
            json={"kb_id": "expert", "content": "Reusable guidance", "level": "tactical", "source": "manual"},
        )
        entries = await client.get("/api/get_knowledge", params={"kb_id": "expert"})
        approved = await client.post("/api/knowledge/entry-1/approve")
        duplicate = await client.post(
            "/api/add_knowledge",
            json={"kb_id": "expert", "content": "  reusable   guidance ", "source": "manual"},
        )

    assert created.status_code == 201
    assert created.json()["verified"] is False
    assert entries.json()[0]["source"] == "manual"
    assert entries.json()[0]["level"] == "tactical"
    assert approved.json() == {"success": True, "verified": True}
    assert duplicate.json() == {"k_id": "entry-1", "duplicate": True, "verified": True}


@pytest.mark.asyncio
async def test_delete_returns_404_when_missing_and_supports_kb_hint(monkeypatch) -> None:
    store = Store()
    store.entry = {"content": "delete me"}
    feedback = Store()
    monkeypatch.setattr(knowledge_routes, "_knowledge_store", store)
    monkeypatch.setattr(knowledge_routes, "_feedback_store", feedback)
    app = FastAPI()
    app.include_router(knowledge_routes.router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        deleted = await client.delete("/api/delete_knowledge", params={"k_id": "entry-1", "kb_id": "expert"})
        repeated = await client.delete("/api/delete_knowledge", params={"k_id": "entry-1", "kb_id": "expert"})

    assert deleted.json() == {"success": True}
    assert repeated.status_code == 404


@pytest.mark.asyncio
async def test_delete_scans_later_feedback_store(monkeypatch) -> None:
    standard = Store()
    feedback = Store()
    feedback.entry = {"content": "feedback"}
    monkeypatch.setattr(knowledge_routes, "_knowledge_store", standard)
    monkeypatch.setattr(knowledge_routes, "_feedback_store", feedback)
    app = FastAPI()
    app.include_router(knowledge_routes.router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        deleted = await client.delete("/api/delete_knowledge", params={"k_id": "entry-1"})

    assert deleted.json() == {"success": True}
    assert feedback.entry is None
