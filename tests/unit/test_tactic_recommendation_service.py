import asyncio

import pytest

from schemas.retrieval import RetrievedItem, RetrievalResult
from services.scenario_service import ScenarioServiceError
from services.tactic_recommendation_service import (
    TacticRecommendationService,
    _summarize_recommendations,
)


class ScenarioService:
    async def get(self, scenario_id):
        return {
            "id": scenario_id,
            "steps": [
                {
                    "step_type": "background",
                    "status": "confirmed",
                    "current_output": "山地夏季",
                },
                {
                    "step_type": "formation",
                    "status": "confirmed",
                    "current_output": "双方旅级编成",
                },
                {"step_type": "task", "status": "draft", "input": {}},
                {"step_type": "final", "status": "empty"},
            ],
        }


class Retriever:
    def __init__(self):
        self.requests = []

    async def retrieve(self, request):
        self.requests.append(request)
        return RetrievalResult(
            items=[
                RetrievedItem(
                    content=f"{request.side} task doctrine",
                    backend="standard",
                    category="task",
                    score=0.91,
                    source=f"{request.side}_task",
                    source_id=f"task-{request.side}",
                    verified=True,
                )
            ]
        )


async def summarizer(context, red_result, blue_result):
    assert red_result.items[0].source == "red_task"
    assert blue_result.items[0].source == "blue_task"
    return {
        "red_objectives": [{"name": "夺控通道", "content": "控制山地交通要点。"}],
        "blue_objectives": [{"name": "固守要点", "content": "依托既设阵地迟滞对方。"}],
        "campaign_tactics": [{"name": "纵深分割", "content": "分阶段割裂对方部署。"}],
        "tactical_tactics": [{"name": "要点伏击", "content": "在狭窄通道设置伏击。"}],
    }


@pytest.mark.asyncio
async def test_recommendations_use_red_and_blue_task_retrieval_and_cache() -> None:
    retriever = Retriever()
    service = TacticRecommendationService(
        ScenarioService(), retriever, summarizer=summarizer
    )

    first = await service.recommend("scenario-1")
    second = await service.recommend("scenario-1")

    assert [(request.category, request.side) for request in retriever.requests] == [
        ("task", "red"),
        ("task", "blue"),
    ]
    assert first.red_objectives[0].label == "夺控通道"
    assert first.red_objectives[0].content == "控制山地交通要点。"
    assert first.red_objectives[0].source == "red_task · AI提炼"
    assert first.red_objectives[0].verified is True
    assert second.cache_hit is True


@pytest.mark.asyncio
async def test_recommendation_snapshots_are_excluded_from_generation_context() -> None:
    class ScenarioWithSnapshots(ScenarioService):
        async def get(self, scenario_id):
            scenario = await super().get(scenario_id)
            scenario["steps"][2]["input"] = {
                "campaign_tactics": {"selected": ["纵深分割"], "custom": []},
                "recommendation_snapshots": {
                    "campaign_tactics": [
                        {"id": "campaign-1", "label": "纵深分割", "content": "历史详情", "source": "历史来源"},
                    ]
                },
            }
            return scenario

    async def assert_context(context, red_result, blue_result):
        assert "recommendation_snapshots" not in context["task_draft"]
        assert context["task_draft"]["campaign_tactics"]["selected"] == ["纵深分割"]
        return await summarizer(context, red_result, blue_result)

    service = TacticRecommendationService(
        ScenarioWithSnapshots(), Retriever(), summarizer=assert_context
    )

    await service.recommend("scenario-1")


@pytest.mark.asyncio
async def test_recommendations_dispatch_direct_tactics_and_objectives() -> None:
    class Dispatcher:
        def __init__(self):
            self.jobs = []

        def dispatch(self, job):
            self.jobs.append(job)
            return True

    dispatcher = Dispatcher()
    service = TacticRecommendationService(
        ScenarioService(), retriever=Retriever(), summarizer=summarizer,
        deposition_dispatcher=dispatcher,
    )

    await service.recommend("scenario-1")

    assert [(job.category, job.side, job.mode) for job in dispatcher.jobs] == [
        ("tactics_campaign", "all", "direct"),
        ("tactics_tactical", "all", "direct"),
        ("task", "red", "direct"),
        ("task", "blue", "direct"),
    ]
    assert dispatcher.jobs[0].title == "纵深分割"
    assert dispatcher.jobs[2].scope == "objective_recommendation"


@pytest.mark.asyncio
async def test_recommendation_timeout_is_configurable(caplog) -> None:
    class SlowRetriever:
        async def retrieve(self, request):
            await asyncio.sleep(2)

    service = TacticRecommendationService(
        ScenarioService(),
        SlowRetriever(),
        summarizer=summarizer,
        timeout_seconds=0.01,
    )

    with pytest.raises(ScenarioServiceError) as exc_info:
        await service.recommend("scenario-1")

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "RECOMMENDATION_UNAVAILABLE"
    assert "event=tactic_recommendation_timeout" in caplog.text


@pytest.mark.asyncio
async def test_ai_summarizer_requests_named_tactic_content() -> None:
    class StructuredModel:
        prompt = ""

        async def ainvoke(self, prompt):
            self.prompt = prompt
            return {
                "red_objectives": [{"name": "夺控通道", "content": "控制交通要点。"}],
                "blue_objectives": [{"name": "纵深防御", "content": "迟滞对方推进。"}],
                "campaign_tactics": [{"name": "分区控制", "content": "衔接各行动阶段。"}],
                "tactical_tactics": [{"name": "侧翼迂回", "content": "利用隐蔽路线机动。"}],
            }

    class Model:
        def __init__(self):
            self.structured = StructuredModel()
            self.schema = None

        def with_structured_output(self, schema):
            self.schema = schema
            return self.structured

    model = Model()
    result = RetrievalResult(
        items=[
            RetrievedItem(
                content='{"title":"任务规划"}',
                backend="lightrag",
                category="task",
                source="red_task",
                source_id="red_task",
            )
        ]
    )

    generated = await _summarize_recommendations(
        {"background": "山地", "formation": "旅级"}, result, result, model=model
    )

    assert generated.campaign_tactics[0].name == "分区控制"
    assert generated.campaign_tactics[0].content == "衔接各行动阶段。"
    assert model.schema is not None
    assert "不得把武器装备型号" in model.structured.prompt
    assert "name（简洁的战法或目标名称）" in model.structured.prompt
