import httpx
import pytest

from schemas.location import LocationResult
from services.location_service import (
    AmapLocationProvider,
    LocationService,
    NominatimLocationProvider,
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
async def test_nominatim_provider_normalizes_response_and_rate_limits() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "place_id": 42,
                    "display_name": "北京市，中国",
                    "lat": "39.9042",
                    "lon": "116.4074",
                    "boundingbox": ["39.4", "41.1", "115.4", "117.5"],
                    "address": {"country": "中国", "state": "北京市"},
                },
                {"place_id": 99, "display_name": "invalid"},
            ],
        )

    now = [0.0]
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = NominatimLocationProvider(
        endpoint="https://example.test/search",
        user_agent="ScenarioAgent-Test/1.0",
        timeout_seconds=1,
        minimum_interval_seconds=1,
        client=client,
        clock=lambda: now[0],
        sleep=fake_sleep,
    )
    try:
        first = await provider.search("北京", 5)
        second = await provider.search("上海", 5)
    finally:
        await client.aclose()

    assert len(first) == len(second) == 1
    assert first[0].model_dump() == {
        "place_id": "nominatim:42",
        "display_name": "北京市，中国",
        "country": "中国",
        "admin1": "北京市",
        "admin2": None,
        "latitude": 39.9042,
        "longitude": 116.4074,
        "bbox": (39.4, 41.1, 115.4, 117.5),
        "source": "nominatim",
    }
    assert sleeps == [1.0]
    assert requests[0].url.params["q"] == "北京"
    assert requests[0].url.params["format"] == "jsonv2"
    assert requests[0].headers["User-Agent"] == "ScenarioAgent-Test/1.0"


@pytest.mark.asyncio
async def test_amap_provider_uses_server_key_and_normalizes_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "1",
                "geocodes": [
                    {
                        "formatted_address": "北京市东城区天安门广场",
                        "province": "北京市",
                        "city": [],
                        "district": "东城区",
                        "location": "116.397455,39.909187",
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AmapLocationProvider(
        endpoint="https://example.test/geocode",
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

    assert len(results) == 1
    assert results[0].display_name == "北京市东城区天安门广场"
    assert results[0].admin1 == "北京市"
    assert results[0].admin2 == "东城区"
    assert results[0].source == "amap"
    assert requests[0].url.params["key"] == "server-secret"
    assert requests[0].url.params["address"] == "天安门"
