import pytest
from pydantic import ValidationError

from schemas.scenario import BackgroundInput, TaskInput


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
                "level": "tactical",
                "red_objective": "hold",
                "blue_objective": "seize",
                "action_types": ["attack"],
                "task_types": ["maneuver"],
                "custom_requirements": "x" * 1001,
            }
        )
