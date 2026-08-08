from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from schemas.location import LocationResult
from services.location_service import (
    LocationProviderError,
    LocationService,
    create_location_service,
)


router = APIRouter(prefix="/api/locations", tags=["locations"])


def get_location_service(request: Request) -> LocationService:
    service = getattr(request.app.state, "location_service", None)
    if service is None:
        service = create_location_service()
        request.app.state.location_service = service
    return service


LocationServiceDependency = Annotated[LocationService, Depends(get_location_service)]


@router.get("/search", response_model=list[LocationResult])
async def search_locations(
    q: Annotated[str, Query(min_length=2, max_length=200)],
    service: LocationServiceDependency,
):
    try:
        return await service.search(q)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_LOCATION_QUERY", "message": str(exc)}},
        )
    except LocationProviderError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "LOCATION_SERVICE_UNAVAILABLE",
                    "message": str(exc),
                }
            },
        )
