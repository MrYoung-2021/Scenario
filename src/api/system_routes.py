from fastapi import APIRouter


router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return process health without calling external services."""
    return {"status": "ok"}
