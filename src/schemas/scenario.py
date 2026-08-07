from enum import StrEnum
from typing import Any, Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class StepType(StrEnum):
    BACKGROUND = "background"
    FORMATION = "formation"
    TASK = "task"
    FINAL = "final"


class StepStatus(StrEnum):
    EMPTY = "empty"
    DRAFT = "draft"
    GENERATING = "generating"
    GENERATED = "generated"
    CONFIRMED = "confirmed"
    STALE = "stale"
    FAILED = "failed"


class GenerationMode(StrEnum):
    GENERATE = "generate"
    REGENERATE = "regenerate"
    REVISE = "revise"


class LocationSelection(BaseModel):
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


class BackgroundInput(BaseModel):
    model_config = {"extra": "forbid"}

    location_mode: Literal["exact_location", "terrain_template"]
    location: LocationSelection | None = None
    terrain_types: list[str] = Field(default_factory=list, max_length=11)
    season: str = Field(min_length=1, max_length=30)
    weather_mode: Literal["inferred", "manual"] = "inferred"
    weather: dict[str, Any] | None = None
    time_condition: str | None = Field(default=None, max_length=100)
    operation_context: str = Field(min_length=1, max_length=50)
    custom_requirements: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_location_mode(self) -> "BackgroundInput":
        if self.location_mode == "exact_location" and self.location is None:
            raise ValueError("exact_location requires a selected location")
        if self.location_mode == "terrain_template" and not self.terrain_types:
            raise ValueError("terrain_template requires at least one terrain type")
        if self.weather_mode == "manual" and not self.weather:
            raise ValueError("manual weather mode requires weather details")
        return self


class SideFormationInput(BaseModel):
    model_config = {"extra": "forbid"}

    role: str = Field(min_length=1, max_length=50)
    branches: list[str] = Field(min_length=1, max_length=20)
    echelon: str = Field(min_length=1, max_length=100)
    approximate_scale: str | None = Field(default=None, max_length=200)
    weapons: list[str] = Field(default_factory=list, max_length=100)
    initial_deployment: str | None = Field(default=None, max_length=500)
    reserve_requirements: str | None = Field(default=None, max_length=500)
    support_requirements: str | None = Field(default=None, max_length=500)
    custom_requirements: str = Field(default="", max_length=1000)


class FormationInput(BaseModel):
    model_config = {"extra": "forbid"}

    scenario_scale: str = Field(min_length=1, max_length=100)
    red: SideFormationInput
    blue: SideFormationInput


class TaskInput(BaseModel):
    model_config = {"extra": "forbid"}

    level: Literal["campaign", "tactical"]
    red_objective: str = Field(min_length=1, max_length=1000)
    blue_objective: str = Field(min_length=1, max_length=1000)
    action_types: list[str] = Field(min_length=1, max_length=20)
    task_types: list[str] = Field(min_length=1, max_length=20)
    phase_template: str | None = Field(default=None, max_length=500)
    trigger_conditions: list[str] = Field(default_factory=list, max_length=20)
    termination_conditions: list[str] = Field(default_factory=list, max_length=20)
    coordination_focus: list[str] = Field(default_factory=list, max_length=20)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    custom_requirements: str = Field(default="", max_length=1000)


StepInput = Annotated[
    BackgroundInput | FormationInput | TaskInput,
    Field(union_mode="left_to_right"),
]


class ScenarioCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class StepInputUpdate(BaseModel):
    input: dict[str, Any]


class ConfirmRequest(BaseModel):
    version: int = Field(ge=1)


class GenerationRequest(BaseModel):
    mode: GenerationMode = GenerationMode.GENERATE
    base_version: int | None = Field(default=None, ge=1)
    revision_instruction: str | None = Field(default=None, max_length=1000)
    request_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_mode_fields(self) -> "GenerationRequest":
        if self.mode == GenerationMode.REVISE:
            if self.base_version is None or not self.revision_instruction:
                raise ValueError(
                    "revise mode requires base_version and revision_instruction"
                )
        elif self.base_version is not None or self.revision_instruction is not None:
            raise ValueError(
                "base_version and revision_instruction are only valid in revise mode"
            )
        return self


class ScenarioSummary(BaseModel):
    id: str
    title: str
    current_step: StepType
    status: str
    created_at: str
    updated_at: str
