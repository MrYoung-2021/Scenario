import httpx
import pytest
from fastapi import FastAPI

from api.location_routes import router
from schemas.location import LocationResult
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
