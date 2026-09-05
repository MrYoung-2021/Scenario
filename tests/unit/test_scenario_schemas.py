import pytest
from pydantic import ValidationError

from schemas.scenario import BackgroundInput, FormationInput, TaskInput


def test_exact_location_requires_selected_result() -> None:
    with pytest.raises(ValidationError, match="selected location"):
        BackgroundInput.model_validate(
            {
                "location_mode": "exact_location",
                "season": "summer",
                "operation_context": "exercise",
            }
        )


def test_terrain_template_requires_a_type() -> None:
    with pytest.raises(ValidationError, match="terrain type"):
        BackgroundInput.model_validate(
            {
                "location_mode": "terrain_template",
                "terrain_types": [],
                "season": "summer",
                "operation_context": "exercise",
            }
        )


def test_custom_requirements_are_limited() -> None:
    with pytest.raises(ValidationError):
        TaskInput.model_validate(
            {
                "red_objective": {"selected": ["hold"], "custom": ""},
                "blue_objective": {"selected": [], "custom": "seize"},
                "campaign_tactics": {"selected": [], "custom": []},
                "tactical_tactics": {"selected": ["maneuver"], "custom": []},
                "custom_requirements": "x" * 1001,
            }
        )


def test_custom_terrain_type_satisfies_template_and_is_deduplicated() -> None:
    value = BackgroundInput.model_validate({
        "location_mode": "terrain_template",
        "terrain_types": [],
        "custom_terrain_types": ["滨海湿地", " 滨海湿地 "],
        "season": "夏",
        "operation_context": "演训",
    })
    assert value.custom_terrain_types == ["滨海湿地"]


def test_new_task_contract_requires_objectives_and_tactic() -> None:
    with pytest.raises(ValidationError):
        TaskInput.model_validate({
            "red_objective": {"selected": [], "custom": ""},
            "blue_objective": {"selected": ["目标"], "custom": ""},
            "campaign_tactics": {"selected": [], "custom": []},
            "tactical_tactics": {"selected": [], "custom": []},
        })


def test_task_recommendation_snapshots_only_retain_selected_items() -> None:
    value = TaskInput.model_validate({
        "red_objective": {"selected": ["夺控要点"], "custom": ""},
        "blue_objective": {"selected": ["固守阵地"], "custom": ""},
        "campaign_tactics": {"selected": ["纵深分割"], "custom": []},
        "tactical_tactics": {"selected": [], "custom": []},
        "recommendation_snapshots": {
            "red_objectives": [
                {"id": "red-1", "label": "夺控要点", "content": "夺取关键区域。", "source": "red_task · AI提炼"},
                {"id": "red-2", "label": "未选择目标", "content": "不应保存。", "source": "red_task · AI提炼"},
            ],
            "blue_objectives": [
                {"id": "blue-1", "label": "固守阵地", "content": "保持防御地域。", "source": "blue_task · AI提炼"},
            ],
            "campaign_tactics": [
                {"id": "campaign-1", "label": "纵深分割", "content": "割裂对方部署。", "source": "战役知识 · AI提炼"},
            ],
        },
    })

    assert [item.id for item in value.recommendation_snapshots.red_objectives] == ["red-1"]
    assert value.recommendation_snapshots.campaign_tactics[0].content == "割裂对方部署。"
    assert value.recommendation_snapshots.tactical_tactics == []


def test_formation_rejects_role_and_merges_custom_weapons() -> None:
    with pytest.raises(ValidationError):
        FormationInput.model_validate({
            "scenario_scale": "营级及以下",
            "red": {"role": "防御", "branches": ["陆军"], "echelon": "营"},
            "blue": {"branches": ["陆军"], "echelon": "营"},
        })
    value = FormationInput.model_validate({
        "scenario_scale": "营级及以下",
        "red": {"branches": ["陆军"], "echelon": "营", "weapons": ["99式"], "custom_weapons": ["99式", "试验装备"]},
        "blue": {"branches": ["陆军"], "echelon": "营"},
    })
    assert value.red.weapons == ["99式", "试验装备"]
