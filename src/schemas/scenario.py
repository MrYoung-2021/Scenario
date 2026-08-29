from enum import StrEnum
from typing import Any, Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.location import LocationProfile, LocationResult


LocationSelection = LocationResult


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


class BackgroundInput(BaseModel):
    model_config = {"extra": "forbid"}

    location_mode: Literal["exact_location", "terrain_template"]
    location: LocationSelection | None = None
    location_profile: LocationProfile | None = None
    terrain_types: list[str] = Field(default_factory=list, max_length=11)
    custom_terrain_types: list[str] = Field(default_factory=list, max_length=10)
    season: str = Field(min_length=1, max_length=30)
    weather_mode: Literal["inferred", "manual"] = "inferred"
    weather: dict[str, Any] | None = None
    time_condition: str | None = Field(default=None, max_length=100)
    operation_context: str = Field(min_length=1, max_length=50)
    custom_requirements: str = Field(default="", max_length=1000)

    @field_validator("terrain_types", "custom_terrain_types")
    @classmethod
    def normalize_terrain_types(cls, values: list[str]) -> list[str]:
        return _unique_text(values, max_item_length=50)

    @model_validator(mode="after")
    def validate_location_mode(self) -> "BackgroundInput":
        if self.location_mode == "exact_location" and self.location is None:
            raise ValueError("exact_location requires a selected location")
        if self.location_mode == "terrain_template" and not (
            self.terrain_types or self.custom_terrain_types
        ):
            raise ValueError("terrain_template requires at least one terrain type")
        if self.weather_mode == "manual" and not self.weather:
            raise ValueError("manual weather mode requires weather details")
        return self


class SideFormationInput(BaseModel):
    model_config = {"extra": "forbid"}

    branches: list[str] = Field(min_length=1, max_length=20)
    echelon: str = Field(min_length=1, max_length=100)
    approximate_scale: str | None = Field(default=None, max_length=200)
    weapons: list[str] = Field(default_factory=list, max_length=100)
    custom_weapons: list[str] = Field(default_factory=list, max_length=50)
    initial_deployment: str | None = Field(default=None, max_length=500)
    reserve_requirements: str | None = Field(default=None, max_length=500)
    support_requirements: str | None = Field(default=None, max_length=500)
    custom_requirements: str = Field(default="", max_length=1000)

    @field_validator("branches", "weapons", "custom_weapons")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        return _unique_text(values, max_item_length=100)

    @model_validator(mode="after")
    def merge_custom_weapons(self) -> "SideFormationInput":
        self.weapons = _unique_text(
            [*self.weapons, *self.custom_weapons], max_item_length=100
        )
        return self


class FormationInput(BaseModel):
    model_config = {"extra": "forbid"}

    scenario_scale: str = Field(min_length=1, max_length=100)
    red: SideFormationInput
    blue: SideFormationInput


class SelectionInput(BaseModel):
    model_config = {"extra": "forbid"}

    selected: list[str] = Field(default_factory=list, max_length=30)
    custom: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("selected", "custom")
    @classmethod
    def normalize_values(cls, values: list[str]) -> list[str]:
        return _unique_text(values, max_item_length=200)


class ObjectiveSelection(BaseModel):
    model_config = {"extra": "forbid"}

    selected: list[str] = Field(default_factory=list, max_length=20)
    custom: str = Field(default="", max_length=1000)

    @field_validator("selected")
    @classmethod
    def normalize_selected(cls, values: list[str]) -> list[str]:
        return _unique_text(values, max_item_length=500)

    @field_validator("custom")
    @classmethod
    def strip_custom(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_objective(self) -> "ObjectiveSelection":
        if not self.selected and not self.custom:
            raise ValueError("objective requires a selected or custom value")
        return self


class TaskInput(BaseModel):
    model_config = {"extra": "forbid"}

    red_objective: ObjectiveSelection
    blue_objective: ObjectiveSelection
    campaign_tactics: SelectionInput = Field(default_factory=SelectionInput)
    tactical_tactics: SelectionInput = Field(default_factory=SelectionInput)
    trigger_conditions: list[str] = Field(default_factory=list, max_length=20)
    termination_conditions: list[str] = Field(default_factory=list, max_length=20)
    coordination_focus: list[str] = Field(default_factory=list, max_length=20)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    custom_requirements: str = Field(default="", max_length=1000)

    @field_validator(
        "trigger_conditions",
        "termination_conditions",
        "coordination_focus",
        "constraints",
    )
    @classmethod
    def normalize_conditions(cls, values: list[str]) -> list[str]:
        return _unique_text(values, max_item_length=300)

    @model_validator(mode="after")
    def require_tactic(self) -> "TaskInput":
        groups = (self.campaign_tactics, self.tactical_tactics)
        if not any(group.selected or group.custom for group in groups):
            raise ValueError("at least one campaign or tactical tactic is required")
        return self


def _unique_text(values: list[str], *, max_item_length: int) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        if len(value) > max_item_length:
            raise ValueError(f"list item exceeds {max_item_length} characters")
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            normalized.append(value)
    return normalized


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
