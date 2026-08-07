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
            raise ScenarioServiceError("SCENARIO_NOT_FOUND", "Scenario not found", 404)
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
        try:
            validated = INPUT_MODELS[step].model_validate(input_data)
        except ValidationError as exc:
            raise ScenarioServiceError(
                "INVALID_STEP_INPUT",
                "Step input validation failed",
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
