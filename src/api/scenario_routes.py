import os
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
from services.retrieval_registry import get_tiered_retriever
from services.retrieval_registry import get_deposition_worker
from services.scenario_service import ScenarioService
from services.tactic_recommendation_service import TacticRecommendationService
from utils.config_handler import ConfigHandler, rag_conf


router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])
options_router = APIRouter(prefix="/api", tags=["scenarios"])

STATIC_SCENARIO_OPTIONS = {
    "terrain_types": [
        {"value": value, "label": value, "builtin": True}
        for value in ("海岛", "沿海", "城市", "山地", "高原", "平原", "丘陵", "森林", "荒漠", "河网", "湖泊")
    ],
    "seasons": ["春", "夏", "秋", "冬", "雨季", "旱季"],
    "operation_contexts": ["演训", "危机", "对抗", "其他"],
    "scenario_scales": ["战区/战役", "师旅级", "营级及以下", "自定义"],
    "branches": ["陆军", "海军", "空军", "火箭军", "无人系统", "电子对抗", "后勤保障"],
    "echelons": ["班", "排", "连", "营", "团", "旅", "师", "军", "战区"],
    "tactic_sources": ["campaign", "tactical"],
}


def load_scenario_options() -> dict:
    return {
        **STATIC_SCENARIO_OPTIONS,
        "weapon_categories": ConfigHandler.load_elements_json(),
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


def get_recommendation_service(request: Request) -> TacticRecommendationService:
    service = getattr(request.app.state, "tactic_recommendation_service", None)
    if service is None:
        repository = ScenarioRepository(request.app.state.sqlite_conn.conn)
        service = TacticRecommendationService(
            ScenarioService(repository),
            get_tiered_retriever(),
            deposition_dispatcher=get_deposition_worker(),
            timeout_seconds=float(
                os.getenv(
                    "TACTIC_RECOMMENDATION_TIMEOUT_SECONDS",
                    rag_conf["retrieval"].get(
                        "tactic_recommendation_timeout_seconds", 180
                    ),
                )
            ),
        )
        request.app.state.tactic_recommendation_service = service
    return service


RecommendationServiceDependency = Annotated[
    TacticRecommendationService,
    Depends(get_recommendation_service),
]


@router.get("/options")
async def scenario_options():
    return load_scenario_options()


@options_router.get("/scenario-options")
async def scenario_options_alias():
    return load_scenario_options()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_scenario(payload: ScenarioCreate, service: ScenarioServiceDependency):
    return await service.create(payload.title)


@router.get("")
async def list_scenarios(service: ScenarioServiceDependency):
    return await service.list()


@router.get("/{scenario_id}")
async def get_scenario(scenario_id: str, service: ScenarioServiceDependency):
    return await service.get(scenario_id)


@router.post("/{scenario_id}/tactic-recommendations")
async def tactic_recommendations(
    scenario_id: str,
    service: RecommendationServiceDependency,
):
    return await service.recommend(scenario_id)


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
