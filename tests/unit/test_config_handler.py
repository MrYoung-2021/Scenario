import json

import pytest

from utils.config_handler import ConfigHandler


def test_element_update_validates_and_deduplicates(tmp_path) -> None:
    path = tmp_path / "elements.json"
    path.write_text('[{"name":"战斗机","elements":["歼-20"]}]', encoding="utf-8")

    assert ConfigHandler.update_elements_json(
        {"name": "战斗机", "element": "F-35"}, path
    ) is True
    assert ConfigHandler.update_elements_json(
        {"name": " 战斗机 ", "element": " f-35 "}, path
    ) is False
    assert json.loads(path.read_text(encoding="utf-8"))[0]["elements"] == [
        "歼-20", "F-35"
    ]

    with pytest.raises(ValueError):
        ConfigHandler.update_elements_json({"name": "", "element": "装备"}, path)
