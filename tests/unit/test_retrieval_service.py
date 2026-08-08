import pytest
import logging

from schemas.retrieval import RetrievedItem, RetrievalQuery
from services.retrieval_service import TieredRetriever


def item(content: str, *, score: float, verified: bool = True, category: str = "environment") -> RetrievedItem:
    return RetrievedItem(
        content=content,
        backend="standard",
        category=category,
        score=score,
        source="manual",
        source_id=content,
        verified=verified,
    )


class StandardBackend:
    def __init__(self, items):
        self.items = items
        self.calls = []

    async def asearch(self, query, *, k, metadata_filter):
        self.calls.append((query, k, metadata_filter))
        return self.items


class LightBackend:
    def __init__(self, content):
        self.content = content
        self.calls = []

    async def query(self, query, *, top_k):
        self.calls.append((query, top_k))
        return self.content


def retriever(standard, fallbacks=None, minimum=1):
    return TieredRetriever(
        standard,
        fallbacks or {},
        score_threshold=0.65,
        standard_top_k=5,
        lightrag_top_k=4,
        minimum_verified_hits=minimum,
    )


@pytest.mark.asyncio
async def test_verified_standard_hits_suppress_lightrag() -> None:
    standard = StandardBackend([item("verified", score=0.88)])
    light = LightBackend("fallback")

    result = await retriever(standard, {"environment": light}).retrieve(
        RetrievalQuery(query="weather", category="environment")
    )

    assert result.used_fallback is False
    assert [entry.content for entry in result.items] == ["verified"]
    assert light.calls == []
    assert standard.calls[0][2] == {"category": "environment"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("items", "reason"),
    [
        ([], "no_standard_hits"),
        ([item("weak", score=0.2)], "low_relevance"),
        ([item("draft", score=0.9, verified=False)], "unverified_only"),
    ],
)
async def test_weak_standard_results_use_matching_fallback(items, reason) -> None:
    light = LightBackend("scoped context")
    result = await retriever(StandardBackend(items), {"environment": light}).retrieve(
        RetrievalQuery(query="weather", category="environment")
    )

    assert result.fallback_reason == reason
    assert result.fallback_scopes == ["environment"]
    assert light.calls == [("weather", 4)]


@pytest.mark.asyncio
async def test_task_queries_both_sides_and_deduplicates_merged_results() -> None:
    duplicate = item("same guidance", score=0.9, verified=False, category="task")
    red = LightBackend("same guidance")
    blue = LightBackend("blue guidance")

    result = await retriever(
        StandardBackend([duplicate]),
        {"red_task": red, "blue_task": blue},
    ).retrieve(RetrievalQuery(query="planning", category="task", side="all"))

    assert result.fallback_scopes == ["red_task", "blue_task"]
    assert [entry.content for entry in result.items] == ["same guidance", "blue guidance"]


@pytest.mark.asyncio
async def test_tactics_level_and_side_route_to_matching_weapon_scope() -> None:
    red = LightBackend("campaign tactics")
    result = await retriever(StandardBackend([]), {"red_weapon": red}).retrieve(
        RetrievalQuery(
            query="campaign maneuver",
            category="tactics_campaign",
            level="campaign",
            side="red",
        )
    )

    assert result.fallback_scopes == ["red_weapon"]
    assert result.items[0].category == "tactics_campaign"


@pytest.mark.asyncio
async def test_retrieval_logs_hit_and_fallback_statistics(caplog) -> None:
    light = LightBackend("fallback")
    with caplog.at_level(logging.INFO, logger="ScenarioAgent"):
        await retriever(StandardBackend([]), {"environment": light}).retrieve(
            RetrievalQuery(query="weather", category="environment")
        )

    assert "event=rag_retrieval" in caplog.text
    assert "standard_hit_count=0" in caplog.text
    assert "lightrag_fallback_count=1" in caplog.text
    assert "lightrag_fallback_rate=1.0" in caplog.text
