import pytest
from pydantic import ValidationError

from schemas.retrieval import StructuredKnowledgeEntry
from services.knowledge_promotion_service import KnowledgePromotionService


class Store:
    def __init__(self):
        self.entries = {}
        self.added = []

    def find_by_content_hash(self, value):
        return self.entries.get(value)

    def add_text(self, text, category, metadata=None):
        knowledge_id = f"knowledge-{len(self.added) + 1}"
        self.added.append((text, category, metadata))
        self.entries[metadata["content_hash"]] = {"k_id": knowledge_id}
        return [knowledge_id]

    def set_verified(self, knowledge_id, verified):
        self.approved = (knowledge_id, verified)
        return True


def structured_entry() -> StructuredKnowledgeEntry:
    return StructuredKnowledgeEntry(
        title="Low visibility reconnaissance",
        category="tactics_tactical",
        level="tactical",
        applicable_conditions=["low visibility"],
        principle="Use redundant observation paths.",
        constraints=["shorten sortie intervals"],
        source="red_weapon",
    )


def test_structured_entry_rejects_missing_principle() -> None:
    with pytest.raises(ValidationError):
        StructuredKnowledgeEntry(title="Invalid", category="expert", source="manual")


def test_promotion_deduplicates_hash_and_defaults_unverified() -> None:
    store = Store()
    service = KnowledgePromotionService(store)

    first = service.promote([structured_entry()], source="red_weapon", source_id="doc-4")
    second = service.promote([structured_entry()], source="red_weapon", source_id="doc-4")

    assert first == [{"k_id": "knowledge-1", "duplicate": False}]
    assert second == [{"k_id": "knowledge-1", "duplicate": True}]
    metadata = store.added[0][2]
    assert metadata["verified"] is False
    assert metadata["source"] == "red_weapon"
    assert metadata["source_id"] == "doc-4"


def test_approval_updates_review_state() -> None:
    store = Store()
    assert KnowledgePromotionService(store).approve("knowledge-1") is True
    assert store.approved == ("knowledge-1", True)

