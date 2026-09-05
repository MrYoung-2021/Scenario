import pytest
import pytest_asyncio
import aiosqlite

from repositories.scenario_repository import ScenarioRepository
from schemas.scenario import GenerationMode, StepStatus, StepType
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


@pytest_asyncio.fixture
async def workflow(tmp_path):
    store = await AsyncConversationStore.create(str(tmp_path / "workflow.db"))
    repository = ScenarioRepository(store.conn)
    try:
        yield store, repository, ScenarioService(repository)
    finally:
        await store.close()


async def generate_and_confirm(service, repository, scenario_id, step, input_data):
    await service.save_input(scenario_id, step, input_data)
    await service.validate_prerequisites(scenario_id, step)
    version = await repository.add_version(
        scenario_id,
        step,
        f"{step} output",
        {},
        [],
        GenerationMode.GENERATE,
    )
    await service.confirm(scenario_id, step, version)
    return version


@pytest.mark.asyncio
async def test_prerequisites_and_version_conflict(workflow) -> None:
    _, repository, service = workflow
    scenario = await service.create("Test scenario")
    scenario_id = scenario["id"]

    with pytest.raises(ScenarioServiceError) as blocked:
        await service.validate_prerequisites(scenario_id, StepType.FORMATION)
    assert blocked.value.code == "PREREQUISITE_NOT_CONFIRMED"

    version = await generate_and_confirm(
        service, repository, scenario_id, StepType.BACKGROUND, BACKGROUND_INPUT
    )
    with pytest.raises(ScenarioServiceError) as conflict:
        await service.confirm(scenario_id, StepType.BACKGROUND, version)
    assert conflict.value.code == "VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_upstream_changes_mark_downstream_stale(workflow) -> None:
    _, repository, service = workflow
    scenario_id = (await service.create("Invalidation"))["id"]
    await generate_and_confirm(service, repository, scenario_id, StepType.BACKGROUND, BACKGROUND_INPUT)
    await generate_and_confirm(service, repository, scenario_id, StepType.FORMATION, FORMATION_INPUT)
    await generate_and_confirm(service, repository, scenario_id, StepType.TASK, TASK_INPUT)
    await repository.add_version(scenario_id, StepType.FINAL, "final", {}, [])

    changed = {**BACKGROUND_INPUT, "season": "winter"}
    scenario = await service.save_input(scenario_id, StepType.BACKGROUND, changed)
    statuses = {step["step_type"]: step["status"] for step in scenario["steps"]}

    assert statuses == {
        "background": StepStatus.DRAFT,
        "formation": StepStatus.STALE,
        "task": StepStatus.STALE,
        "final": StepStatus.STALE,
    }


@pytest.mark.asyncio
async def test_formation_change_only_invalidates_task_and_final(workflow) -> None:
    _, repository, service = workflow
    scenario_id = (await service.create("Formation invalidation"))["id"]
    await generate_and_confirm(service, repository, scenario_id, StepType.BACKGROUND, BACKGROUND_INPUT)
    await generate_and_confirm(service, repository, scenario_id, StepType.FORMATION, FORMATION_INPUT)
    await generate_and_confirm(service, repository, scenario_id, StepType.TASK, TASK_INPUT)
    await repository.add_version(scenario_id, StepType.FINAL, "final", {}, [])

    changed = {
        **FORMATION_INPUT,
        "red": {**FORMATION_INPUT["red"], "echelon": "company"},
    }
    scenario = await service.save_input(scenario_id, StepType.FORMATION, changed)
    statuses = {step["step_type"]: step["status"] for step in scenario["steps"]}

    assert statuses == {
        "background": StepStatus.CONFIRMED,
        "formation": StepStatus.DRAFT,
        "task": StepStatus.STALE,
        "final": StepStatus.STALE,
    }


@pytest.mark.asyncio
async def test_delete_removes_legacy_task_config(workflow) -> None:
    store, _, service = workflow
    scenario_id = (await service.create("Delete me"))["id"]
    await store.create_conversation_with_id(scenario_id)
    await store.set_config_field(scenario_id, "background", "legacy")

    await service.delete(scenario_id)

    cursor = await store.conn.execute(
        "SELECT 1 FROM task_configs WHERE conversation_id = ?", (scenario_id,)
    )
    assert await cursor.fetchone() is None


@pytest.mark.asyncio
async def test_delete_transaction_rolls_back_on_failure(workflow) -> None:
    store, repository, service = workflow
    scenario_id = (await service.create("Rollback"))["id"]
    await service.save_input(scenario_id, StepType.BACKGROUND, BACKGROUND_INPUT)
    await repository.add_version(scenario_id, StepType.BACKGROUND, "draft", {}, [])
    await store.conn.execute(
        """
        CREATE TRIGGER prevent_scenario_delete BEFORE DELETE ON scenarios
        BEGIN SELECT RAISE(ABORT, 'blocked'); END
        """
    )
    await store.conn.commit()

    with pytest.raises(aiosqlite.IntegrityError):
        await service.delete(scenario_id)

    assert await repository.get(scenario_id) is not None
    assert len(await repository.list_versions(scenario_id, StepType.BACKGROUND)) == 1


@pytest.mark.asyncio
async def test_legacy_inputs_are_saved_in_new_contract(workflow) -> None:
    _, _, service = workflow
    scenario_id = (await service.create("Legacy input"))["id"]
    scenario = await service.save_input(scenario_id, StepType.FORMATION, FORMATION_INPUT)
    formation = scenario["steps"][1]["input"]
    assert "role" not in formation["red"]
    assert formation["red"]["custom_weapons"] == []

    scenario = await service.save_input(scenario_id, StepType.TASK, TASK_INPUT)
    task = scenario["steps"][2]["input"]
    assert not {"level", "action_types", "task_types", "phase_template"} & task.keys()
    assert task["red_objective"]["custom"] == "hold terrain"
    assert task["tactical_tactics"]["selected"] == ["attack", "maneuver"]
    assert task["recommendation_snapshots"] == {
        "red_objectives": [],
        "blue_objectives": [],
        "campaign_tactics": [],
        "tactical_tactics": [],
    }


@pytest.mark.asyncio
async def test_task_recommendation_snapshots_are_persisted(workflow) -> None:
    _, _, service = workflow
    scenario_id = (await service.create("Recommendation snapshots"))["id"]
    task_input = {
        "red_objective": {"selected": ["夺控要点"], "custom": ""},
        "blue_objective": {"selected": ["固守阵地"], "custom": ""},
        "campaign_tactics": {"selected": ["纵深分割"], "custom": []},
        "tactical_tactics": {"selected": [], "custom": []},
        "recommendation_snapshots": {
            "red_objectives": [
                {"id": "red-1", "label": "夺控要点", "content": "夺取关键区域。", "source": "red_task · AI提炼"},
            ],
            "blue_objectives": [
                {"id": "blue-1", "label": "固守阵地", "content": "保持防御地域。", "source": "blue_task · AI提炼"},
            ],
            "campaign_tactics": [
                {"id": "campaign-1", "label": "纵深分割", "content": "割裂对方部署。", "source": "战役知识 · AI提炼"},
            ],
        },
    }

    saved = await service.save_input(scenario_id, StepType.TASK, task_input)
    task = saved["steps"][2]["input"]

    assert task["recommendation_snapshots"]["red_objectives"][0] == {
        "id": "red-1",
        "label": "夺控要点",
        "content": "夺取关键区域。",
        "source": "red_task · AI提炼",
    }
    assert task["recommendation_snapshots"]["campaign_tactics"][0]["content"] == "割裂对方部署。"
