from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from repositories.scenario_repository import ScenarioRepository
from schemas.scenario import ConfirmRequest, ScenarioCreate, StepInputUpdate, StepType
from services.scenario_service import ScenarioService


router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


def get_scenario_service(request: Request) -> ScenarioService:
    return ScenarioService(ScenarioRepository(request.app.state.sqlite_conn.conn))


ScenarioServiceDependency = Annotated[ScenarioService, Depends(get_scenario_service)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_scenario(payload: ScenarioCreate, service: ScenarioServiceDependency):
    return await service.create(payload.title)


@router.get("")
async def list_scenarios(service: ScenarioServiceDependency):
    return await service.list()


@router.get("/{scenario_id}")
async def get_scenario(scenario_id: str, service: ScenarioServiceDependency):
    return await service.get(scenario_id)


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(scenario_id: str, service: ScenarioServiceDependency):
    await service.delete(scenario_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{scenario_id}/steps/{step}/input")
async def save_step_input(
    scenario_id: str,
    step: StepType,
    payload: StepInputUpdate,
    service: ScenarioServiceDependency,
):
    return await service.save_input(scenario_id, step, payload.input)


@router.post("/{scenario_id}/steps/{step}/confirm")
async def confirm_step(
    scenario_id: str,
    step: StepType,
    payload: ConfirmRequest,
    service: ScenarioServiceDependency,
):
    return await service.confirm(scenario_id, step, payload.version)


@router.get("/{scenario_id}/steps/{step}/versions")
async def list_step_versions(
    scenario_id: str,
    step: StepType,
    service: ScenarioServiceDependency,
):
    return await service.versions(scenario_id, step)
