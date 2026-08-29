import json
import os
import tempfile
import yaml
from utils.path_tools import get_abs_path

class ConfigHandler(object):
    @staticmethod
    def load_rag_config(config_path: str=get_abs_path("config/rag.yml"), encoding="utf-8"):
        with open(config_path, "r", encoding=encoding) as f:
            return yaml.load(f.read(), Loader=yaml.FullLoader)

    @staticmethod
    def load_db_config(config_path: str=get_abs_path("config/db.yml"), encoding="utf-8"):
        with open(config_path, "r", encoding=encoding) as f:
            return yaml.load(f.read(), Loader=yaml.FullLoader)

    @staticmethod
    def load_prompts_config(config_path: str=get_abs_path("config/prompts.yml"), encoding="utf-8"):
        with open(config_path, "r", encoding=encoding) as f:
            return yaml.load(f.read(), Loader=yaml.FullLoader)

    @staticmethod
    def load_agent_config(config_path: str = get_abs_path("config/agent.yml"), encoding="utf-8"):
        with open(config_path, "r", encoding=encoding) as f:
            return yaml.load(f.read(), Loader=yaml.FullLoader)

    @staticmethod
    def load_location_config(config_path: str = get_abs_path("config/location.yml"), encoding="utf-8"):
        with open(config_path, "r", encoding=encoding) as f:
            return yaml.load(f.read(), Loader=yaml.FullLoader)
        
    @staticmethod
    def load_elements_json(config_path: str = get_abs_path("config/elements.json"), encoding="utf-8"):
        with open(config_path, "r", encoding=encoding) as f:
            return json.load(f)
    @staticmethod   
    def update_elements_json(new_entry, file_path=get_abs_path("config/elements.json")) -> bool:
        # 1. 读取现有数据
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            data = []   # 文件不存在则初始化为空列表

        if not isinstance(data, list):
            raise ValueError("JSON 文件顶层结构应为列表")

        name = str(new_entry.get("name", "")).strip()
        new_element = str(new_entry.get("element", "")).strip()
        if not name or len(name) > 50:
            raise ValueError("装备分类名称必须为 1 到 50 个字符")
        if not new_element or len(new_element) > 100:
            raise ValueError("装备名称必须为 1 到 100 个字符")

        # 2. 查找 name 相同的条目并更新
        updated = False
        for item in data:
            if str(item.get('name', '')).casefold() == name.casefold():
                # 确保 elements 键存在
                existing_elements = item.setdefault('elements', [])
                # 去重添加
                if not any(str(value).casefold() == new_element.casefold() for value in existing_elements):
                    existing_elements.append(new_element)
                else:
                    return False
                updated = True
                break

        # 3. 若 name 不存在，则新增条目
        if not updated:
            data.append({
                'name': name,
                'elements': [new_element]
            })

        # 4. 写回文件
        directory = os.path.dirname(os.path.abspath(file_path))
        fd, temp_path = tempfile.mkstemp(prefix="elements-", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
        return True

    @staticmethod
    def delete_category(name, file_path = get_abs_path("config/elements.json")):

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return False   # 文件不存在，无需删除

        original_len = len(data)
        data = [item for item in data if item.get('name') != name]
        
        if len(data) == original_len:
            return False   # 没有找到匹配的 name

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True

    @staticmethod
    def delete_element(name, element, file_path = get_abs_path("config/elements.json")):

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return False

        for item in data:
            if item.get('name') == name:
                elements = item.get('elements', [])
                if element in elements:
                    elements.remove(element)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    return True
                else:
                    return False   # 元素不存在

        return False   # name 不存在


rag_conf = ConfigHandler.load_rag_config()
db_conf = ConfigHandler.load_db_config()
prompts_conf = ConfigHandler.load_prompts_config()
agent_conf = ConfigHandler.load_agent_config()
location_conf = ConfigHandler.load_location_config()
