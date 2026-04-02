import glob
import os
from utils.config_handler import prompts_conf
from utils.path_tools import get_abs_path, get_skills_path
from utils.logger import get_logger

logger = get_logger()


def load_json_examples(folder_path=get_skills_path(), encoding='utf-8', separator='\n'):
    if not os.path.isdir(folder_path):
        logger.error(f"json示例文件夹{folder_path}不存在")
        raise FileNotFoundError(f"json示例文件夹不存在: {folder_path}")

    # 构建匹配模式
    pattern = os.path.join(folder_path, "*.json")
    json_files = glob.glob(pattern)

    contents = []
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
                if content:                     # 避免空文件添加多余分隔符
                    contents.append(content)
        except Exception as e:
            logger.error("载入json示例失败")
            raise RuntimeError(f"读取json示例文件失败 {file_path}: {e}")
            # 静默跳过

    return separator.join(contents)

def load_text_examples(folder_path=get_skills_path(), encoding='utf-8', separator='\n'):
    if not os.path.isdir(folder_path):
        logger.error(f"文本示例文件夹{folder_path}不存在")
        raise FileNotFoundError(f"文本示例文件夹不存在: {folder_path}")

    # 构建匹配模式
    pattern = os.path.join(folder_path, "*.md")
    json_files = glob.glob(pattern)

    contents = []
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
                if content:                     # 避免空文件添加多余分隔符
                    contents.append(content)
        except Exception as e:
            logger.error("载入文本示例失败")
            raise RuntimeError(f"读取文本示例文件失败 {file_path}: {e}")
            # 静默跳过

    return separator.join(contents)