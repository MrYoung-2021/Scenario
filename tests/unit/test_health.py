import httpx
import pytest
from fastapi import FastAPI

from api.system_routes import router


@pytest.mark.asyncio
async def test_health_check_returns_ok() -> None:
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
