from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from repositories.scenario_repository import STEP_ORDER, ScenarioRepository
from schemas.scenario import (
    BackgroundInput,
    FormationInput,
    StepStatus,
    StepType,
    TaskInput,
)


INPUT_MODELS = {
    StepType.BACKGROUND: BackgroundInput,
    StepType.FORMATION: FormationInput,
    StepType.TASK: TaskInput,
}

PREREQUISITES = {
    StepType.BACKGROUND: (),
    StepType.FORMATION: (StepType.BACKGROUND,),
    StepType.TASK: (StepType.BACKGROUND, StepType.FORMATION),
    StepType.FINAL: (StepType.BACKGROUND, StepType.FORMATION, StepType.TASK),
}


class ScenarioServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, **details: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class ScenarioService:
    def __init__(self, repository: ScenarioRepository):
        self.repository = repository

    async def create(self, title: str) -> dict[str, Any]:
        scenario_id = await self.repository.create(title.strip())
        return await self.get(scenario_id)

    async def list(self) -> list[dict[str, Any]]:
        return await self.repository.list()

    async def get(self, scenario_id: str) -> dict[str, Any]:
        scenario = await self.repository.get(scenario_id)
        if scenario is None:
            raise ScenarioServiceError("SCENARIO_NOT_FOUND", "想定项目不存在", 404)
        for item in scenario["steps"]:
            step = StepType(item["step_type"])
            if step != StepType.FINAL:
                item["input"] = normalize_step_input(step, item["input"])
        return scenario

    async def save_input(
        self,
        scenario_id: str,
        step: StepType,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        if step == StepType.FINAL:
            raise ScenarioServiceError("STEP_HAS_NO_INPUT", "Final step has no editable input")
        scenario = await self.get(scenario_id)
        current_step = next(item for item in scenario["steps"] if item["step_type"] == step)
        if current_step["status"] == StepStatus.GENERATING:
            raise ScenarioServiceError(
                "GENERATION_IN_PROGRESS",
                "Step input cannot be changed while generation is running",
                409,
                step=step,
            )
        normalized = normalize_step_input(step, input_data)
        try:
            validated = INPUT_MODELS[step].model_validate(normalized)
        except ValidationError as exc:
            raise ScenarioServiceError(
                "INVALID_STEP_INPUT",
                "步骤输入校验失败",
                422,
                errors=exc.errors(include_url=False),
            ) from exc
        await self.repository.save_input(scenario_id, step, validated.model_dump(mode="json"))
        return await self.get(scenario_id)

    async def validate_prerequisites(self, scenario_id: str, step: StepType) -> None:
        scenario = await self.get(scenario_id)
        statuses = {item["step_type"]: item["status"] for item in scenario["steps"]}
        for required in PREREQUISITES[step]:
            if statuses[required] != StepStatus.CONFIRMED:
                raise ScenarioServiceError(
                    "PREREQUISITE_NOT_CONFIRMED",
                    f"Required step '{required}' is not confirmed",
                    409,
                    required_step=required,
                )

    async def confirm(self, scenario_id: str, step: StepType, version: int) -> dict[str, Any]:
        await self.get(scenario_id)
        await self.validate_prerequisites(scenario_id, step)
        if not await self.repository.confirm(scenario_id, step, version):
            raise ScenarioServiceError(
                "VERSION_CONFLICT",
                "The requested version is no longer current",
                409,
                version=version,
            )
        return await self.get(scenario_id)

    async def versions(self, scenario_id: str, step: StepType) -> list[dict[str, Any]]:
        await self.get(scenario_id)
        return await self.repository.list_versions(scenario_id, step)

    async def delete(self, scenario_id: str) -> None:
        if not await self.repository.delete(scenario_id):
            raise ScenarioServiceError("SCENARIO_NOT_FOUND", "Scenario not found", 404)


def normalize_step_input(step: StepType, input_data: dict[str, Any]) -> dict[str, Any]:
    """Adapt legacy draft inputs without mutating stored historical versions."""
    data = dict(input_data or {})
    if step == StepType.BACKGROUND:
        data.setdefault("custom_terrain_types", [])
        return data
    if step == StepType.FORMATION:
        for side in ("red", "blue"):
            value = data.get(side)
            if isinstance(value, dict):
                normalized_side = dict(value)
                normalized_side.pop("role", None)
                normalized_side.setdefault("custom_weapons", [])
                data[side] = normalized_side
        return data
    if step != StepType.TASK:
        return data

    legacy_tactics = [
        *data.get("action_types", []),
        *data.get("task_types", []),
    ]
    for objective in ("red_objective", "blue_objective"):
        value = data.get(objective)
        if isinstance(value, str):
            data[objective] = {"selected": [], "custom": value}
    data.setdefault("campaign_tactics", {"selected": [], "custom": []})
    data.setdefault(
        "tactical_tactics",
        {"selected": legacy_tactics, "custom": []},
    )
    for key in (
        "red_campaign_tactics",
        "blue_campaign_tactics",
        "red_tactical_tactics",
        "blue_tactical_tactics",
    ):
        data.setdefault(key, {"selected": [], "custom": []})
    for key in ("level", "action_types", "task_types", "phase_template"):
        data.pop(key, None)
    return data
