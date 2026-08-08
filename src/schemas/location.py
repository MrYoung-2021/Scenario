from pydantic import BaseModel, Field


class LocationResult(BaseModel):
    model_config = {"extra": "forbid"}

    place_id: str = Field(min_length=1, max_length=300)
    display_name: str = Field(min_length=1, max_length=500)
    country: str | None = Field(default=None, max_length=100)
    admin1: str | None = Field(default=None, max_length=100)
    admin2: str | None = Field(default=None, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    bbox: tuple[float, float, float, float] | None = None
    source: str = Field(min_length=1, max_length=50)
