"""Asynchronous, bounded promotion of retrieved and generated knowledge."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from schemas.retrieval import DepositionJob, StructuredKnowledgeEntry
from services.knowledge_promotion_service import KnowledgePromotionService

logger = logging.getLogger("ScenarioAgent")


class JobSummarizer(Protocol):
    async def summarize(self, job: DepositionJob) -> list[StructuredKnowledgeEntry]: ...


class AIKnowledgeSummarizer:
    def __init__(self, model: Any | None = None, prompt: str | None = None) -> None:
        self.model = model
        self.prompt = prompt or (
            Path(__file__).resolve().parents[1] / "prompts" / "knowledge_summary_prompt.txt"
        ).read_text(encoding="utf-8")

    async def summarize(self, job: DepositionJob) -> list[StructuredKnowledgeEntry]:
        model = self.model
        if model is None:
            from models.factory import mini_model

            model = mini_model
        if model is None:
            raise RuntimeError("知识沉淀总结模型未配置")
        prompt = (
            f"{self.prompt}\n\n受控目标：{json.dumps({
                'category': job.category,
                'level': job.level,
                'side': job.side,
                'domain': job.domain,
                'scenario_type': job.scenario_type,
            }, ensure_ascii=False)}\n"
            f"查询：{job.query[:4000]}\n参考资料：{job.content[:24000]}"
        )
        # A small wrapper keeps the model contract easy to replace in tests.
        class Entries(BaseModel):
            entries: list[StructuredKnowledgeEntry]

        response = await model.with_structured_output(Entries).ainvoke(prompt)
        parsed = Entries.model_validate(response)
        accepted: list[StructuredKnowledgeEntry] = []
        for entry in parsed.entries:
            if entry.category != job.category:
                continue
            accepted.append(
                entry.model_copy(
                    update={
                        "category": job.category,
                        "level": job.level if job.level != "general" else entry.level,
                        "side": job.side,
                        "domain": job.domain,
                        "scenario_type": job.scenario_type,
                        "source": job.source,
                    }
                )
            )
        return accepted


class KnowledgeDepositionWorker:
    def __init__(
        self,
        promoter: KnowledgePromotionService,
        summarizer: JobSummarizer,
        *,
        queue_size: int = 100,
        worker_count: int = 2,
        max_summary_entries: int = 8,
    ) -> None:
        self.promoter = promoter
        self.summarizer = summarizer
        self.queue: asyncio.Queue[DepositionJob | None] = asyncio.Queue(maxsize=max(1, queue_size))
        self.worker_count = max(1, worker_count)
        self.max_summary_entries = max(1, max_summary_entries)
        self._tasks: list[asyncio.Task[None]] = []
        self._keys: set[str] = set()
        self._accepting = False

    async def start(self) -> None:
        if self._tasks:
            return
        self._accepting = True
        self._tasks = [asyncio.create_task(self._run(), name=f"knowledge-deposition-{i}") for i in range(self.worker_count)]

    def dispatch(self, job: DepositionJob) -> bool:
        if not self._accepting:
            logger.info("event=knowledge_deposition_dropped reason=worker_not_started category=%s", job.category)
            return False
        key = hashlib.sha256(
            f"{job.mode}|{job.category}|{job.side}|{job.scope}|{job.content.strip().casefold()}".encode("utf-8")
        ).hexdigest()
        if key in self._keys:
            logger.info("event=knowledge_deposition_duplicate category=%s side=%s scope=%s", job.category, job.side, job.scope)
            return False
        try:
            self.queue.put_nowait(job)
        except asyncio.QueueFull:
            logger.warning("event=knowledge_deposition_dropped reason=queue_full category=%s side=%s scope=%s", job.category, job.side, job.scope)
            return False
        self._keys.add(key)
        logger.info("event=knowledge_deposition_enqueued category=%s side=%s scope=%s mode=%s queue_depth=%s", job.category, job.side, job.scope, job.mode, self.queue.qsize())
        return True

    async def _run(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                if job is None:
                    return
                await self._process(job)
            except Exception:
                logger.exception("event=knowledge_deposition_failed category=%s side=%s scope=%s", getattr(job, "category", "unknown"), getattr(job, "side", "unknown"), getattr(job, "scope", "unknown"))
            finally:
                self.queue.task_done()

    async def _process(self, job: DepositionJob) -> None:
        if job.mode == "direct":
            entries = [StructuredKnowledgeEntry(
                title=job.title or job.content[:200], category=job.category, level=job.level,
                principle=job.content, source=job.source, domain=job.domain,
                side=job.side, scenario_type=job.scenario_type,
            )]
        else:
            entries = (await self.summarizer.summarize(job))[: self.max_summary_entries]
        results = await asyncio.to_thread(
            self.promoter.promote,
            entries,
            source=job.source,
            source_id=job.source_id,
            extra_metadata={
                "source_scope": job.scope,
                "source_backend": "generated" if job.mode == "direct" else "lightrag",
                "deposition_mode": job.mode,
                "context_hash": job.context_hash,
            },
        )
        logger.info("event=knowledge_deposition_succeeded category=%s side=%s scope=%s mode=%s entries=%s", job.category, job.side, job.scope, job.mode, len(results))

    async def stop(self, timeout_seconds: float = 10.0) -> None:
        self._accepting = False
        if not self._tasks:
            return
        timed_out = False
        try:
            await asyncio.wait_for(self.queue.join(), timeout=max(0.1, timeout_seconds))
        except asyncio.TimeoutError:
            timed_out = True
            logger.warning("event=knowledge_deposition_shutdown_timeout queue_depth=%s", self.queue.qsize())
        if timed_out:
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
            return
        for _ in self._tasks:
            try:
                self.queue.put_nowait(None)
            except asyncio.QueueFull:
                break
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
