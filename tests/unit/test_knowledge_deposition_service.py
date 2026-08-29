import asyncio

import pytest

from schemas.retrieval import DepositionJob, StructuredKnowledgeEntry
from services.knowledge_deposition_service import KnowledgeDepositionWorker


class Store:
    def __init__(self):
        self.added = []

    def find_by_content_hash(self, value):
        return None

    def add_text(self, text, category, metadata=None):
        self.added.append((text, category, metadata))
        return [f"id-{len(self.added)}"]


class Promoter:
    def __init__(self):
        self.calls = []

    def promote(self, entries, *, source, source_id, extra_metadata=None):
        self.calls.append((entries, source, source_id, extra_metadata))
        return [{"k_id": "id-1", "duplicate": False}]


class Summarizer:
    def __init__(self):
        self.calls = []

    async def summarize(self, job):
        self.calls.append(job)
        return [StructuredKnowledgeEntry(
            title="总结", category=job.category, level=job.level,
            principle="可复用内容", source=job.scope, side=job.side,
        )]


@pytest.mark.asyncio
async def test_worker_summarizes_and_direct_writes_without_blocking() -> None:
    promoter = Promoter()
    summarizer = Summarizer()
    worker = KnowledgeDepositionWorker(promoter, summarizer, queue_size=2, worker_count=1)
    await worker.start()
    assert worker.dispatch(DepositionJob(
        content="raw", category="environment", scope="environment",
        source_id="source-1", source="environment",
    ))
    await asyncio.wait_for(worker.queue.join(), timeout=1)
    await worker.stop()
    assert len(summarizer.calls) == 1
    assert promoter.calls[0][3]["source_backend"] == "lightrag"


@pytest.mark.asyncio
async def test_worker_direct_mode_skips_summarizer() -> None:
    promoter = Promoter()
    summarizer = Summarizer()
    worker = KnowledgeDepositionWorker(promoter, summarizer, worker_count=1)
    await worker.start()
    assert worker.dispatch(DepositionJob(
        title="战法", content="直接内容", category="tactics_campaign",
        level="campaign", scope="tactic_recommendation",
        source_id="tactic-1", source="tactic_recommendation", mode="direct",
    ))
    await asyncio.wait_for(worker.queue.join(), timeout=1)
    await worker.stop()
    assert summarizer.calls == []
    assert promoter.calls[0][0][0].title == "战法"
