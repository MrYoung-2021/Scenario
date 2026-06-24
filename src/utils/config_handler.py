import json
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
    def load_elements_json(config_path: str = get_abs_path("config/elements.json"), encoding="utf-8"):
        with open(config_path, "r", encoding=encoding) as f:
            return json.load(f)
    @staticmethod   
    def update_elements_json(new_entry, file_path=get_abs_path("config/elements.json")):
        # 1. 读取现有数据
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            data = []   # 文件不存在则初始化为空列表

        if not isinstance(data, list):
            raise ValueError("JSON 文件顶层结构应为列表")

        new_element = new_entry.get('element')
        if not new_element:
            # 元素为空或不存在，不进行任何操作
            return

        # 2. 查找 name 相同的条目并更新
        updated = False
        for item in data:
            if item.get('name') == new_entry['name']:
                # 确保 elements 键存在
                existing_elements = item.setdefault('elements', [])
                # 去重添加
                if new_element not in existing_elements:
                    existing_elements.append(new_element)
                updated = True
                break

        # 3. 若 name 不存在，则新增条目
        if not updated:
            data.append({
                'name': new_entry['name'],
                'elements': [new_element]
            })

        # 4. 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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