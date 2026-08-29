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
