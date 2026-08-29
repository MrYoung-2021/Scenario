import httpx
import pytest
from datetime import datetime, timezone
from fastapi import FastAPI

from api.location_routes import router
from schemas.location import LocationProfile, LocationResult
from services.location_service import LocationProviderError, LocationService


class ApiProvider:
    name = "api-test"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def search(self, query: str, limit: int) -> list[LocationResult]:
        if self.fail:
            raise LocationProviderError("测试地址服务不可用")
        return [
            LocationResult(
                place_id="api:beijing",
                display_name=f"{query}市",
                country="中国",
                admin1=f"{query}市",
                latitude=39.9042,
                longitude=116.4074,
                source=self.name,
            )
        ]

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_location_search_api_uses_injected_provider() -> None:
    app = FastAPI()
    app.state.location_service = LocationService(ApiProvider())
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        too_short = await client.get("/api/locations/search", params={"q": "北"})
        result = await client.get("/api/locations/search", params={"q": "北京"})

    assert too_short.status_code == 422
    assert result.status_code == 200
    assert result.json()[0]["place_id"] == "api:beijing"
    assert result.json()[0]["display_name"] == "北京市"


@pytest.mark.asyncio
async def test_location_search_api_returns_structured_unavailable_error() -> None:
    app = FastAPI()
    app.state.location_service = LocationService(ApiProvider(fail=True))
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await client.get("/api/locations/search", params={"q": "北京"})

    assert result.status_code == 503
    assert result.json()["error"]["code"] == "LOCATION_SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_location_profile_api_returns_typical_snapshot() -> None:
    async def loader(location, season):
        return LocationProfile(
            place_id=location.place_id,
            geography={"terrain": "山前平原"},
            climate={"seasonal_temperature": f"{season}季典型温度"},
            source="环境知识库",
            updated_at=datetime.now(timezone.utc),
        )

    app = FastAPI()
    app.state.location_service = LocationService(ApiProvider(), profile_loader=loader)
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    payload = {
        "location": {
            "place_id": "amap:beijing", "display_name": "北京市", "country": "中国",
            "admin1": "北京市", "latitude": 39.9042, "longitude": 116.4074, "source": "amap",
        },
        "season": "夏",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await client.post("/api/locations/profile", json=payload)

    assert result.status_code == 200
    assert result.json()["data_kind"] == "typical"
    assert result.json()["geography"]["terrain"] == "山前平原"


@pytest.mark.asyncio
async def test_location_profile_api_accepts_amap_location_outside_china() -> None:
    async def loader(location, season):
        return LocationProfile(
            place_id=location.place_id,
            geography={"terrain": "沿海平原与低丘相间。"},
            climate={"seasonal_temperature": "典型海洋性气候。"},
            source="环境知识库",
            updated_at=datetime.now(timezone.utc),
        )

    app = FastAPI()
    app.state.location_service = LocationService(ApiProvider(), profile_loader=loader)
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    payload = {
        "location": {
            "place_id": "amap:overseas", "display_name": "海外测试地点",
            "country": None, "admin1": None, "latitude": 60.0,
            "longitude": 150.0, "source": "amap",
        }
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await client.post("/api/locations/profile", json=payload)

    assert result.status_code == 200
    assert result.json()["place_id"] == "amap:overseas"
