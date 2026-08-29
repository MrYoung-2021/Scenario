from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LocationResult(BaseModel):
    model_config = {"extra": "forbid"}

    place_id: str = Field(min_length=1, max_length=300)
    display_name: str = Field(min_length=1, max_length=500)
    address: str | None = Field(default=None, max_length=500)
    country: str | None = Field(default=None, max_length=100)
    admin1: str | None = Field(default=None, max_length=100)
    admin2: str | None = Field(default=None, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    bbox: tuple[float, float, float, float] | None = None
    source: str = Field(min_length=1, max_length=50)


class LocationProfile(BaseModel):
    model_config = {"extra": "forbid"}

    place_id: str
    geography: dict[str, str]
    climate: dict[str, str]
    source: str
    updated_at: datetime
    data_kind: Literal["typical", "realtime"] = "typical"
    notice: str = "内容由 AI 基于环境知识资料总结，为典型特征，不代表实时天气"


class LocationProfileSummary(BaseModel):
    model_config = {"extra": "forbid"}

    geography: str = Field(min_length=1, max_length=2000)
    climate: str = Field(min_length=1, max_length=2000)


class LocationProfileRequest(BaseModel):
    location: LocationResult
    season: str | None = Field(default=None, max_length=30)
