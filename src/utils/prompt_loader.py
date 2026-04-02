from utils.config_handler import prompts_conf
from utils.path_tools import get_abs_path, get_skills_path
from utils.logger import get_logger

logger = get_logger()


def load_system_prompt():
    try:
        system_prompt_path = get_abs_path(prompts_conf["system_prompt_path"])
    except KeyError as e:
        logger.error(f"[load_system_prompt]解析系统提示词文件路径失败。")
        raise e

    try:
        return open(system_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[load_system_prompt]系统提示词文件{system_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[load_system_prompt]解析系统提示词{system_prompt_path}失败. {str(e)}")
        raise e

    
def load_summary_prompt():
    try:
        rag_summarize_prompt_path = get_abs_path(prompts_conf["rag_summarize_prompt_path"])
    except KeyError as e:
        logger.error(f"[rag_summarize_prompt_path]解析总结提示词文件路径失败。")
        raise e

    try:
        return open(rag_summarize_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[rag_summarize_prompt_path]总结提示词文件{rag_summarize_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[rag_summarize_prompt_path]解析总结提示词{rag_summarize_prompt_path}失败. {str(e)}")
        raise e
    
def load_scenario_prompt():
    try:
        scenario_prompt_path = get_abs_path(prompts_conf["scenario_prompt_path"])
    except KeyError as e:
        logger.error(f"[scenario_prompt_path]解析想定提示词文件路径失败。")
        raise e
    
    try:
        return open(scenario_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[scenario_prompt_path]想定提示词文件{scenario_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[scenario_prompt_path]解析想定提示词{scenario_prompt_path}失败. {str(e)}")
        raise e

def load_text_prompt():
    try:
        text_prompt_path = get_abs_path(prompts_conf["text_prompt_path"])
    except KeyError as e:
        logger.error(f"[text_prompt_path]解析文本提示词文件路径失败。")
        raise e
    
    try:
        return open(text_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[text_prompt_path]文本提示词文件{text_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[text_prompt_path]解析文本提示词{text_prompt_path}失败. {str(e)}")
        raise e