import httpx
import pytest
from datetime import datetime, timezone

from schemas.location import LocationProfile, LocationProfileSummary, LocationResult
from schemas.retrieval import RetrievedItem, RetrievalResult
from services.location_service import (
    AmapLocationProvider,
    LocationService,
    _load_location_profile,
    _summarize_location_knowledge,
)


class FakeProvider:
    name = "fake"

    def __init__(self, results: list[LocationResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []
        self.closed = False

    async def search(self, query: str, limit: int) -> list[LocationResult]:
        self.calls.append((query, limit))
        return self.results

    async def close(self) -> None:
        self.closed = True


def location_result() -> LocationResult:
    return LocationResult(
        place_id="fake:1",
        display_name="北京市，中国",
        country="中国",
        admin1="北京市",
        latitude=39.9042,
        longitude=116.4074,
        bbox=(39.4, 41.1, 115.4, 117.5),
        source="fake",
    )


@pytest.mark.asyncio
async def test_location_service_normalizes_and_caches_queries() -> None:
    now = [100.0]
    provider = FakeProvider([location_result()])
    service = LocationService(
        provider,
        cache_ttl_seconds=10,
        result_limit=6,
        clock=lambda: now[0],
    )

    first = await service.search("  Bei   Jing ")
    second = await service.search("bei jing")
    assert first == second
    assert provider.calls == [("Bei Jing", 6)]

    now[0] = 111.0
    await service.search("BEI JING")
    assert provider.calls[-1] == ("BEI JING", 6)
    assert len(provider.calls) == 2

    await service.close()
    assert provider.closed is True


@pytest.mark.asyncio
async def test_amap_provider_uses_server_key_and_normalizes_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "1",
                "tips": [
                    {
                        "id": "B000A816R6",
                        "name": "天安门广场",
                        "address": "北京市东城区西长安街",
                        "city": ["北京市"],
                        "district": "东城区",
                        "location": "116.397455,39.909187",
                    },
                    {
                        "id": "INVALID",
                        "name": "海外测试地点",
                        "address": "International Test Address",
                        "city": [],
                        "district": "",
                        "location": "150.0,60.0",
                    },
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AmapLocationProvider(
        endpoint="https://example.test/v3/assistant/inputtips",
        api_key="server-secret",
        user_agent="ScenarioAgent-Test/1.0",
        timeout_seconds=1,
        minimum_interval_seconds=0,
        client=client,
    )
    try:
        results = await provider.search("天安门", 8)
    finally:
        await client.aclose()

    assert len(results) == 2
    assert results[0].display_name == "天安门广场"
    assert results[0].address == "北京市东城区西长安街"
    assert results[0].admin1 == "北京市"
    assert results[0].admin2 == "东城区"
    assert results[0].source == "amap"
    assert results[1].display_name == "海外测试地点"
    assert results[1].country is None
    assert results[1].admin1 is None
    assert results[1].latitude == 60.0
    assert results[1].longitude == 150.0
    assert requests[0].url.params["key"] == "server-secret"
    assert requests[0].url.params["keywords"] == "天安门"
    assert requests[0].url.params["output"] == "json"
    assert requests[0].url.params["datatype"] == "all"
    assert requests[0].url.path.endswith("/inputtips")


@pytest.mark.asyncio
async def test_location_profile_is_cached() -> None:
    calls = []

    async def load_profile(location, season):
        calls.append((location.place_id, season))
        return LocationProfile(
            place_id=location.place_id,
            geography={"terrain": "平原"},
            climate={"seasonal_temperature": "温带季风气候"},
            source="环境知识库",
            updated_at=datetime.now(timezone.utc),
        )

    location = location_result().model_copy(update={"place_id": "amap:beijing", "source": "amap"})
    service = LocationService(FakeProvider([]), profile_loader=load_profile)
    first = await service.profile(location, "夏")
    second = await service.profile(location, "夏")

    assert first == second
    assert calls == [("amap:beijing", "夏")]


@pytest.mark.asyncio
async def test_location_profile_accepts_amap_location_outside_china() -> None:
    async def load_profile(location, season):
        return LocationProfile(
            place_id=location.place_id,
            geography={"terrain": "海岸城市，地势较平缓。"},
            climate={"seasonal_temperature": "典型海洋性气候。"},
            source="环境知识库",
            updated_at=datetime.now(timezone.utc),
        )

    location = location_result().model_copy(update={
        "place_id": "amap:overseas",
        "display_name": "海外测试地点",
        "country": None,
        "admin1": None,
        "latitude": 60.0,
        "longitude": 150.0,
        "source": "amap",
    })
    service = LocationService(FakeProvider([]), profile_loader=load_profile)

    profile = await service.profile(location)

    assert profile.place_id == "amap:overseas"


@pytest.mark.asyncio
async def test_location_profile_rejects_non_amap_location() -> None:
    service = LocationService(FakeProvider([]))
    with pytest.raises(ValueError, match="高德"):
        await service.profile(location_result())


@pytest.mark.asyncio
async def test_location_profile_returns_ai_summary_instead_of_raw_json() -> None:
    class FakeRetriever:
        async def retrieve(self, request):
            return RetrievalResult(items=[RetrievedItem(
                content='{"terrain":"山地","temperature":"10-20C","metadata":{"source":"raw"}}',
                backend="standard",
                category="environment",
                source="环境资料",
                source_id="env-1",
                score=0.9,
                verified=True,
            )])

    captured = {}

    async def summarize(location, season, documents):
        captured["documents"] = documents
        return LocationProfileSummary(
            geography="该地区以山地为主，地势起伏明显，交通通行易受地形制约。",
            climate="当地气温随海拔变化明显，降水和低能见度天气可能影响行动。",
        )

    location = location_result().model_copy(update={"place_id": "amap:test", "source": "amap"})
    profile = await _load_location_profile(
        location,
        "秋",
        retriever=FakeRetriever(),
        summarizer=summarize,
    )

    assert captured["documents"][0].startswith("{")
    assert profile.geography["terrain"].startswith("该地区以山地为主")
    assert profile.climate["seasonal_temperature"].startswith("当地气温")
    assert "{" not in profile.geography["terrain"]


@pytest.mark.asyncio
async def test_ai_summarizer_requests_readable_structured_content() -> None:
    class FakeStructuredModel:
        def __init__(self):
            self.prompt = ""

        async def ainvoke(self, prompt):
            self.prompt = prompt
            return {
                "geography": "沿海平原与丘陵相间，河网和道路较为密集。",
                "climate": "夏季温暖多雨，强风和低能见度天气需要重点关注。",
            }

    class FakeModel:
        def __init__(self):
            self.structured = FakeStructuredModel()
            self.schema = None

        def with_structured_output(self, schema):
            self.schema = schema
            return self.structured

    model = FakeModel()
    location = location_result().model_copy(update={"place_id": "amap:test", "source": "amap"})
    summary = await _summarize_location_knowledge(
        location,
        "夏",
        ['{"terrain":"coastal plain"}'],
        model=model,
    )

    assert model.schema is LocationProfileSummary
    assert summary.geography.startswith("沿海平原")
    assert "不要输出 JSON" in model.structured.prompt
