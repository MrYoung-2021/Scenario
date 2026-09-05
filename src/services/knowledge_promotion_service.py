"""Validation, normalization, and review for reusable knowledge."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Protocol

from schemas.retrieval import StructuredKnowledgeEntry


class KnowledgeStore(Protocol):
    def find_by_content_hash(self, content_hash: str, category: str | None = None) -> dict | None: ...
    def add_text(self, text: str, category: str, metadata: dict | None = None) -> list[str]: ...
    def set_verified(self, knowledge_id: str, verified: bool) -> bool: ...


class KnowledgeSummarizer(Protocol):
    async def summarize(self, content: str, *, source: str) -> list[StructuredKnowledgeEntry]: ...


def normalize_knowledge_content(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip().casefold()


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_knowledge_content(content).encode("utf-8")).hexdigest()


class KnowledgePromotionService:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    async def summarize_and_promote(
        self,
        content: str,
        *,
        source: str,
        source_id: str,
        summarizer: KnowledgeSummarizer,
    ) -> list[dict]:
        entries = await summarizer.summarize(content, source=source)
        return self.promote(entries, source=source, source_id=source_id)

    def promote(
        self,
        entries: list[StructuredKnowledgeEntry],
        *,
        source: str,
        source_id: str,
        extra_metadata: dict | None = None,
    ) -> list[dict]:
        results: list[dict] = []
        for entry in entries:
            document = json.dumps(entry.model_dump(), ensure_ascii=False, sort_keys=True)
            digest = content_hash(document)
            try:
                existing = self.store.find_by_content_hash(digest, entry.category)
            except TypeError:
                existing = self.store.find_by_content_hash(digest)
            if existing:
                results.append({"k_id": existing["k_id"], "duplicate": True})
                continue
            metadata = {
                "level": entry.level,
                "domain": entry.domain,
                "side": entry.side,
                "scenario_type": entry.scenario_type,
                "source": source,
                "source_id": source_id,
                "verified": False,
                "content_hash": digest,
            }
            if extra_metadata:
                metadata.update(extra_metadata)
            ids = self.store.add_text(
                document,
                entry.category,
                metadata,
            )
            results.extend({"k_id": knowledge_id, "duplicate": False} for knowledge_id in ids)
        return results

    def approve(self, knowledge_id: str) -> bool:
        return self.store.set_verified(knowledge_id, True)

