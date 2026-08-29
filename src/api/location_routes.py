from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from schemas.location import LocationProfile, LocationProfileRequest, LocationResult
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


@router.post("/profile", response_model=LocationProfile)
async def location_profile(
    payload: LocationProfileRequest,
    service: LocationServiceDependency,
):
    try:
        return await service.profile(payload.location, payload.season)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_LOCATION", "message": str(exc)}},
        )
    except LocationProviderError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "LOCATION_PROFILE_UNAVAILABLE",
                    "message": str(exc),
                }
            },
        )


@router.get("/profile", response_model=LocationProfile)
async def get_location_profile(
    place_id: Annotated[str, Query(min_length=1, max_length=300)],
    display_name: Annotated[str, Query(min_length=1, max_length=500)],
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    service: LocationServiceDependency,
    country: str | None = None,
    address: str | None = None,
    admin1: str | None = None,
    admin2: str | None = None,
    season: str | None = None,
):
    payload = LocationResult(
        place_id=place_id,
        display_name=display_name,
        address=address,
        country=country,
        admin1=admin1,
        admin2=admin2,
        latitude=latitude,
        longitude=longitude,
        source="amap",
    )
    try:
        return await service.profile(payload, season)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_LOCATION", "message": str(exc)}},
        )
    except LocationProviderError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "LOCATION_PROFILE_UNAVAILABLE",
                    "message": str(exc),
                }
            },
        )
