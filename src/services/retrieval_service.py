"""Standard-first retrieval with scoped LightRAG fallback."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Protocol

from schemas.retrieval import DepositionJob, RetrievedItem, RetrievalQuery, RetrievalResult


logger = logging.getLogger("ScenarioAgent")


class StandardKnowledgeBackend(Protocol):
    async def asearch(
        self,
        query: str,
        *,
        k: int,
        metadata_filter: dict[str, object],
    ) -> list[RetrievedItem]: ...


class LightKnowledgeBackend(Protocol):
    async def query(self, query: str, *, top_k: int) -> str: ...


class DepositionDispatcher(Protocol):
    def dispatch(self, job: DepositionJob) -> bool: ...


class LazyLightRAGBackend:
    """Create one LightRAG wrapper per scope, on its first actual fallback."""

    def __init__(self, factory: Callable[[], object]) -> None:
        self._factory = factory
        self._wrapper: object | None = None

    async def query(self, query: str, *, top_k: int) -> str:
        if self._wrapper is None:
            self._wrapper = self._factory()
        return await self._wrapper.aquery(
            query,
            top_k=top_k,
            only_need_context=True,
        )


class TieredRetriever:
    def __init__(
        self,
        standard: StandardKnowledgeBackend,
        fallbacks: dict[str, LightKnowledgeBackend],
        *,
        score_threshold: float,
        standard_top_k: int,
        lightrag_top_k: int,
        minimum_verified_hits: int,
        deposition_dispatcher: DepositionDispatcher | None = None,
    ) -> None:
        self.standard = standard
        self.fallbacks = fallbacks
        self.score_threshold = score_threshold
        self.standard_top_k = standard_top_k
        self.lightrag_top_k = lightrag_top_k
        self.minimum_verified_hits = minimum_verified_hits
        self.deposition_dispatcher = deposition_dispatcher

    async def retrieve(self, request: RetrievalQuery) -> RetrievalResult:
        standard_items = await self.standard.asearch(
            request.query,
            k=self.standard_top_k,
            metadata_filter=request.metadata_filter(),
        )
        eligible = self._deduplicate(
            item for item in standard_items if (item.score or 0.0) >= self.score_threshold
        )
        verified = [item for item in eligible if item.verified]
        reason = self._fallback_reason(standard_items, eligible, verified)
        scopes = self._fallback_scopes(request) if reason else []

        fallback_items: list[RetrievedItem] = []
        for scope in scopes:
            backend = self.fallbacks.get(scope)
            if backend is None:
                continue
            content = (await backend.query(request.query, top_k=self.lightrag_top_k)).strip()
            if not content:
                continue
            fallback_source_id = hashlib.sha256(
                f"{scope}|{request.query}|{content}".encode("utf-8")
            ).hexdigest()
            fallback_items.append(
                RetrievedItem(
                    content=content,
                    backend="lightrag",
                    category=request.category,
                    source=scope,
                    source_id=fallback_source_id,
                    metadata={"scope": scope},
                )
            )
            self._dispatch_deposition(request, scope, content)

        standard_hit_count = len(verified)
        fallback_count = len(fallback_items)
        logger.info(
            "event=rag_retrieval category=%s standard_hit_count=%s standard_candidate_count=%s "
            "lightrag_fallback_count=%s lightrag_fallback_rate=%s fallback_reason=%s",
            request.category,
            standard_hit_count,
            len(standard_items),
            fallback_count,
            1.0 if scopes else 0.0,
            reason or "none",
        )
        return RetrievalResult(
            items=self._deduplicate([*eligible, *fallback_items]),
            used_fallback=bool(scopes),
            fallback_reason=reason,
            fallback_scopes=scopes,
        )

    def _dispatch_deposition(self, request: RetrievalQuery, scope: str, content: str) -> None:
        if self.deposition_dispatcher is None or request.category.startswith("tactics_"):
            return
        if request.category == "environment":
            side = "all"
        elif request.side in {"red", "blue"}:
            side = request.side
        else:
            side = "red" if scope.startswith("red_") else "blue"
        source_id = hashlib.sha256(
            f"{scope}|{request.query}|{content}".encode("utf-8")
        ).hexdigest()
        job = DepositionJob(
            query=request.query,
            content=content,
            category=request.category,
            side=side,
            scope=scope,
            source_id=source_id,
            source=scope,
            level=request.level or "general",
            domain=request.domain or "general",
            scenario_type=request.scenario_type or "all",
            context_hash=hashlib.sha256(request.query.encode("utf-8")).hexdigest(),
        )
        try:
            self.deposition_dispatcher.dispatch(job)
        except Exception:
            logger.exception("event=knowledge_deposition_failed reason=dispatch_exception category=%s scope=%s", request.category, scope)

    def _fallback_reason(
        self,
        raw: list[RetrievedItem],
        eligible: list[RetrievedItem],
        verified: list[RetrievedItem],
    ) -> str | None:
        if len(verified) >= self.minimum_verified_hits:
            return None
        if not raw:
            return "no_standard_hits"
        if not eligible:
            return "low_relevance"
        if not verified:
            return "unverified_only"
        return "insufficient_verified_hits"

    @staticmethod
    def _fallback_scopes(request: RetrievalQuery) -> list[str]:
        if request.category == "environment":
            return ["environment"]
        if request.category in {"formation", "weapon", "tactics_campaign", "tactics_tactical", "task"}:
            domain = "weapon" if request.category.startswith("tactics_") else request.category
            sides = [request.side] if request.side in {"red", "blue"} else ["red", "blue"]
            return [f"{side}_{domain}" for side in sides]
        return []

    @staticmethod
    def _deduplicate(items) -> list[RetrievedItem]:
        selected: dict[str, RetrievedItem] = {}
        for item in items:
            normalized = re.sub(r"\s+", " ", item.content).strip().casefold()
            key = item.metadata.get("content_hash") or hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            current = selected.get(str(key))
            if current is None or TieredRetriever._priority(item) > TieredRetriever._priority(current):
                selected[str(key)] = item
        return list(selected.values())

    @staticmethod
    def _priority(item: RetrievedItem) -> tuple[int, int, float]:
        return (
            int(item.backend == "standard"),
            int(item.verified),
            item.score or 0.0,
        )
