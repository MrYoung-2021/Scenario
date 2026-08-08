from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from repositories.scenario_repository import ScenarioRepository
from schemas.scenario import (
    ConfirmRequest,
    GenerationRequest,
    ScenarioCreate,
    StepInputUpdate,
    StepType,
)
from services.generation_service import GenerationService, encode_ndjson
from services.scenario_service import ScenarioService


router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])
options_router = APIRouter(prefix="/api", tags=["scenarios"])

SCENARIO_OPTIONS = {
    "terrain_types": ["海岛", "沿海", "城市", "山地", "高原", "平原", "丘陵", "森林", "荒漠", "河网", "湖泊"],
    "seasons": ["春", "夏", "秋", "冬", "雨季", "旱季"],
    "operation_contexts": ["演训", "危机", "对抗", "其他"],
    "scenario_scales": ["战区/战役", "师旅级", "营级及以下", "自定义"],
    "branches": ["陆军", "海军", "空军", "火箭军", "无人系统", "电子对抗", "后勤保障"],
    "roles": ["进攻", "防御", "机动", "保障", "自定义"],
    "levels": ["campaign", "tactical"],
    "action_types": ["进攻", "防御", "机动", "保障", "侦察", "对抗"],
    "task_types": ["联合火力打击", "区域防御", "跨区机动", "侦察监视", "要点控制", "综合保障"],
}


def get_scenario_service(request: Request) -> ScenarioService:
    return ScenarioService(ScenarioRepository(request.app.state.sqlite_conn.conn))


ScenarioServiceDependency = Annotated[ScenarioService, Depends(get_scenario_service)]


def get_generation_service(request: Request) -> GenerationService:
    repository = ScenarioRepository(request.app.state.sqlite_conn.conn)
    generator = getattr(request.app.state, "scenario_generator", None)
    if generator is None:
        from agents.new_agent import LangChainScenarioGenerator

        generator = LangChainScenarioGenerator()
    return GenerationService(repository, ScenarioService(repository), generator)


GenerationServiceDependency = Annotated[
    GenerationService,
    Depends(get_generation_service),
]


@router.get("/options")
async def scenario_options():
    return SCENARIO_OPTIONS


@options_router.get("/scenario-options")
async def scenario_options_alias():
    return SCENARIO_OPTIONS


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


@router.post("/{scenario_id}/steps/{step}/generate")
async def generate_step(
    scenario_id: str,
    step: StepType,
    payload: GenerationRequest,
    service: GenerationServiceDependency,
):
    prepared = await service.prepare(scenario_id, step, payload)
    return StreamingResponse(
        encode_ndjson(service.stream_events(prepared)),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/{scenario_id}/finalize")
async def finalize_scenario(
    scenario_id: str,
    payload: GenerationRequest,
    service: GenerationServiceDependency,
):
    prepared = await service.prepare(scenario_id, StepType.FINAL, payload)
    return StreamingResponse(
        encode_ndjson(service.stream_events(prepared)),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{scenario_id}/steps/{step}/versions")
async def list_step_versions(
    scenario_id: str,
    step: StepType,
    service: ScenarioServiceDependency,
):
    return await service.versions(scenario_id, step)
