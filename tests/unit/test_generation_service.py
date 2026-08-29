from collections.abc import AsyncIterator
from typing import Any
import asyncio

import pytest
import pytest_asyncio
from pydantic import ValidationError

from repositories.scenario_repository import ScenarioRepository
from schemas.scenario import GenerationMode, GenerationRequest, StepType
from services.generation_service import GenerationService
from services.scenario_service import ScenarioService, ScenarioServiceError
from utils.chat_history_handler import AsyncConversationStore


BACKGROUND_INPUT = {
    "location_mode": "terrain_template",
    "terrain_types": ["mountain"],
    "season": "summer",
    "operation_context": "exercise",
}

FORMATION_INPUT = {
    "scenario_scale": "battalion",
    "red": {"role": "defense", "branches": ["army"], "echelon": "battalion"},
    "blue": {"role": "attack", "branches": ["army"], "echelon": "battalion"},
}

TASK_INPUT = {
    "level": "tactical",
    "red_objective": "hold terrain",
    "blue_objective": "seize terrain",
    "action_types": ["attack"],
    "task_types": ["maneuver"],
}


class FakeGenerator:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        step,
        mode,
        input_data,
        confirmed_context,
        current_output=None,
        revision_instruction=None,
    ) -> AsyncIterator[str | dict[str, Any]]:
        self.calls.append(
            {
                "step": step,
                "mode": mode,
                "input": input_data,
                "context": confirmed_context,
                "current_output": current_output,
                "revision_instruction": revision_instruction,
            }
        )
        if self.fail:
            raise RuntimeError("model unavailable")
        yield {
            "source": {
                "backend": "standard",
                "category": str(step),
                "id": "source-1",
            }
        }
        yield "generated "
        yield "content"


class CancelledGenerator:
    async def stream(self, *args, **kwargs) -> AsyncIterator[str]:
        yield "partial"
        raise asyncio.CancelledError


@pytest_asyncio.fixture
async def generation_workflow(tmp_path):
    store = await AsyncConversationStore.create(str(tmp_path / "generation.db"))
    repository = ScenarioRepository(store.conn)
    scenario_service = ScenarioService(repository)
    generator = FakeGenerator()
    generation_service = GenerationService(repository, scenario_service, generator)
    try:
        yield repository, scenario_service, generation_service, generator
    finally:
        await store.close()


async def collect(service: GenerationService, prepared) -> list[dict[str, Any]]:
    return [event async for event in service.stream_events(prepared)]


@pytest.mark.asyncio
async def test_generation_persists_version_sources_and_replays(generation_workflow) -> None:
    repository, scenario_service, generation_service, generator = generation_workflow
    scenario_id = (await scenario_service.create("Generate"))["id"]
    await scenario_service.save_input(scenario_id, StepType.BACKGROUND, BACKGROUND_INPUT)
    request = GenerationRequest(request_id="request-1")

    events = await collect(
        generation_service,
        await generation_service.prepare(scenario_id, StepType.BACKGROUND, request),
    )

    assert [event["type"] for event in events] == [
        "progress",
        "progress",
        "source",
        "content",
        "content",
        "done",
    ]
    assert events[-1]["version"] == 1
    version = await repository.get_version(scenario_id, StepType.BACKGROUND, 1)
    assert version["output_text"] == "generated content"
    assert version["sources"][0]["id"] == "source-1"
    assert version["input_snapshot"] == BACKGROUND_INPUT | {
        "custom_requirements": "",
        "terrain_types": ["mountain"],
        "weather_mode": "inferred",
        "weather": None,
        "time_condition": None,
        "location": None,
        "location_profile": None,
        "custom_terrain_types": [],
    }
    assert events[0]["message"] == "正在准备前置条件和知识检索"
    assert events[1]["message"] == "正在生成背景与环境"

    replay_events = await collect(
        generation_service,
        await generation_service.prepare(scenario_id, StepType.BACKGROUND, request),
    )
    assert replay_events == [
        {"type": "done", "version": 1, "status": "generated", "replayed": True}
    ]
    assert len(generator.calls) == 1
    with pytest.raises(ScenarioServiceError) as reused:
        await generation_service.prepare(
            scenario_id,
            StepType.BACKGROUND,
            GenerationRequest(
                mode=GenerationMode.REGENERATE,
                request_id="request-1",
            ),
        )
    assert reused.value.code == "REQUEST_ID_CONFLICT"


@pytest.mark.asyncio
async def test_failure_keeps_last_successful_version(generation_workflow) -> None:
    repository, scenario_service, generation_service, _ = generation_workflow
    scenario_id = (await scenario_service.create("Failure"))["id"]
    await scenario_service.save_input(scenario_id, StepType.BACKGROUND, BACKGROUND_INPUT)
    first = GenerationRequest(request_id="successful")
    await collect(
        generation_service,
        await generation_service.prepare(scenario_id, StepType.BACKGROUND, first),
    )

    failing_generator = FakeGenerator(fail=True)
    failing_service = GenerationService(repository, scenario_service, failing_generator)
    retry = GenerationRequest(
        mode=GenerationMode.REGENERATE,
        request_id="failed-regeneration",
    )
    events = await collect(
        failing_service,
        await failing_service.prepare(scenario_id, StepType.BACKGROUND, retry),
    )

    assert events[-1]["type"] == "error"
    scenario = await scenario_service.get(scenario_id)
    assert scenario["steps"][0]["status"] == "failed"
    assert scenario["steps"][0]["current_version"] == 1
    assert scenario["steps"][0]["current_output"] == "generated content"
    assert len(await repository.list_versions(scenario_id, StepType.BACKGROUND)) == 1

    replay = await collect(
        failing_service,
        await failing_service.prepare(scenario_id, StepType.BACKGROUND, retry),
    )
    assert replay[0]["type"] == "error"
    assert replay[0]["replayed"] is True
    assert len(failing_generator.calls) == 1


@pytest.mark.asyncio
async def test_confirmed_context_snapshot_is_passed_to_downstream(generation_workflow) -> None:
    repository, scenario_service, generation_service, generator = generation_workflow
    scenario_id = (await scenario_service.create("Context"))["id"]
    await scenario_service.save_input(scenario_id, StepType.BACKGROUND, BACKGROUND_INPUT)
    await collect(
        generation_service,
        await generation_service.prepare(
            scenario_id,
            StepType.BACKGROUND,
            GenerationRequest(request_id="background"),
        ),
    )
    await scenario_service.confirm(scenario_id, StepType.BACKGROUND, 1)
    await scenario_service.save_input(scenario_id, StepType.FORMATION, FORMATION_INPUT)
    await collect(
        generation_service,
        await generation_service.prepare(
            scenario_id,
            StepType.FORMATION,
            GenerationRequest(request_id="formation"),
        ),
    )

    context = generator.calls[-1]["context"]
    assert context["background"]["version"] == 1
    assert context["background"]["output"] == "generated content"
    version = await repository.get_version(scenario_id, StepType.FORMATION, 1)
    assert version["context_snapshot"] == context


@pytest.mark.asyncio
async def test_prerequisite_and_concurrent_generation_are_blocked(generation_workflow) -> None:
    _, scenario_service, generation_service, _ = generation_workflow
    scenario_id = (await scenario_service.create("Blocked"))["id"]
    await scenario_service.save_input(scenario_id, StepType.FORMATION, FORMATION_INPUT)
    with pytest.raises(ScenarioServiceError) as prerequisite:
        await generation_service.prepare(
            scenario_id,
            StepType.FORMATION,
            GenerationRequest(request_id="blocked"),
        )
    assert prerequisite.value.code == "PREREQUISITE_NOT_CONFIRMED"

    await scenario_service.save_input(scenario_id, StepType.BACKGROUND, BACKGROUND_INPUT)
    await generation_service.prepare(
        scenario_id,
        StepType.BACKGROUND,
        GenerationRequest(request_id="running"),
    )
    with pytest.raises(ScenarioServiceError) as locked_input:
        await scenario_service.save_input(
            scenario_id,
            StepType.BACKGROUND,
            {**BACKGROUND_INPUT, "season": "winter"},
        )
    assert locked_input.value.code == "GENERATION_IN_PROGRESS"
    with pytest.raises(ScenarioServiceError) as duplicate:
        await generation_service.prepare(
            scenario_id,
            StepType.BACKGROUND,
            GenerationRequest(request_id="running"),
        )
    assert duplicate.value.code == "GENERATION_IN_PROGRESS"
    with pytest.raises(ScenarioServiceError) as second:
        await generation_service.prepare(
            scenario_id,
            StepType.BACKGROUND,
            GenerationRequest(request_id="second"),
        )
    assert second.value.code == "GENERATION_IN_PROGRESS"


@pytest.mark.asyncio
async def test_complete_generation_revision_and_finalization_flow(generation_workflow) -> None:
    repository, scenario_service, generation_service, generator = generation_workflow
    scenario_id = (await scenario_service.create("Complete flow"))["id"]

    async def generate_confirm(step, input_data, request_id):
        if input_data is not None:
            await scenario_service.save_input(scenario_id, step, input_data)
        events = await collect(
            generation_service,
            await generation_service.prepare(
                scenario_id,
                step,
                GenerationRequest(request_id=request_id),
            ),
        )
        version = events[-1]["version"]
        await scenario_service.confirm(scenario_id, step, version)
        return version

    await generate_confirm(StepType.BACKGROUND, BACKGROUND_INPUT, "flow-background")
    await generate_confirm(StepType.FORMATION, FORMATION_INPUT, "flow-formation")
    await generate_confirm(StepType.TASK, TASK_INPUT, "flow-task")

    revision = GenerationRequest(
        mode=GenerationMode.REVISE,
        base_version=1,
        revision_instruction="Clarify the second phase",
        request_id="flow-task-revision",
    )
    revision_events = await collect(
        generation_service,
        await generation_service.prepare(scenario_id, StepType.TASK, revision),
    )
    assert revision_events[-1]["version"] == 2
    assert generator.calls[-1]["current_output"] == "generated content"
    assert generator.calls[-1]["revision_instruction"] == "Clarify the second phase"
    scenario_after_revision = await scenario_service.get(scenario_id)
    assert scenario_after_revision["steps"][3]["status"] == "stale"
    await scenario_service.confirm(scenario_id, StepType.TASK, 2)

    final_events = await collect(
        generation_service,
        await generation_service.prepare(
            scenario_id,
            StepType.FINAL,
            GenerationRequest(request_id="flow-final"),
        ),
    )
    assert final_events[-1]["version"] == 1
    await scenario_service.confirm(scenario_id, StepType.FINAL, 1)

    scenario = await scenario_service.get(scenario_id)
    assert scenario["status"] == "finalized"
    assert scenario["final_output"] == "generated content"
    final_version = await repository.get_version(scenario_id, StepType.FINAL, 1)
    assert set(final_version["context_snapshot"]) == {"background", "formation", "task"}


def test_revise_request_requires_version_and_instruction() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(mode="revise", request_id="invalid")


@pytest.mark.asyncio
async def test_interrupted_stream_marks_run_failed(generation_workflow) -> None:
    repository, scenario_service, _, _ = generation_workflow
    scenario_id = (await scenario_service.create("Interrupted"))["id"]
    await scenario_service.save_input(scenario_id, StepType.BACKGROUND, BACKGROUND_INPUT)
    service = GenerationService(repository, scenario_service, CancelledGenerator())
    prepared = await service.prepare(
        scenario_id,
        StepType.BACKGROUND,
        GenerationRequest(request_id="cancelled"),
    )

    with pytest.raises(asyncio.CancelledError):
        await collect(service, prepared)

    run = await repository.get_generation_run("cancelled")
    assert run["status"] == "failed"
    assert run["error_code"] == "GENERATION_CANCELLED"
    scenario = await scenario_service.get(scenario_id)
    assert scenario["steps"][0]["status"] == "failed"
    assert scenario["steps"][0]["current_version"] is None
