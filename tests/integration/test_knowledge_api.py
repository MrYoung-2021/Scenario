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
        self.entry = None
        return True


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

