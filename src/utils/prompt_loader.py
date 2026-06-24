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
        summary_prompt_path = get_abs_path(prompts_conf["summary_prompt_path"])
    except KeyError as e:
        logger.error(f"[summary_prompt_path]解析总结提示词文件路径失败。")
        raise e

    try:
        return open(summary_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[summary_prompt_path]总结提示词文件{summary_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[summary_prompt_path]解析总结提示词{summary_prompt_path}失败. {str(e)}")
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
    
def load_start_prompt():
    try:
        start_prompt_path = get_abs_path(prompts_conf["start_prompt_path"])
    except KeyError as e:
        logger.error(f"[start_prompt_path]解析提示词文件路径失败。")
        raise e
    
    try:
        return open(start_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[start_prompt_path]提示词文件{start_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[start_prompt_path]解析提示词{start_prompt_path}失败. {str(e)}")
        raise e
    
def load_task_prompt():
    try:
        task_prompt_path = get_abs_path(prompts_conf["task_prompt_path"])
    except KeyError as e:
        logger.error(f"[task_prompt_path]解析提示词文件路径失败。")
        raise e
    
    try:
        return open(task_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[task_prompt_path]提示词文件{task_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[task_prompt_path]解析提示词{task_prompt_path}失败. {str(e)}")
        raise e
    
def load_background_prompt():
    try:
        background_prompt_path = get_abs_path(prompts_conf["background_prompt_path"])
    except KeyError as e:
        logger.error(f"[main_prompt_path]解析提示词文件路径失败。")
        raise e
    
    try:
        return open(background_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[background_prompt_path]提示词文件{background_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[background_prompt_path]解析提示词{background_prompt_path}失败. {str(e)}")
        raise e
    
def load_environment_prompt():
    try:
        environment_prompt_path = get_abs_path(prompts_conf["environment_prompt_path"])
    except KeyError as e:
        logger.error(f"[environment_prompt_path]解析提示词文件路径失败。")
        raise e
    
    try:
        return open(environment_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[environment_prompt_path]提示词文件{environment_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[environment_prompt_path]解析提示词{environment_prompt_path}失败. {str(e)}")
        raise e
    
def load_formation_prompt():
    try:
        formation_prompt_path = get_abs_path(prompts_conf["formation_prompt_path"])
    except KeyError as e:
        logger.error(f"[formation_prompt_path]解析提示词文件路径失败。")
        raise e
    
    try:
        return open(formation_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[formation_prompt_path]提示词文件{formation_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[formation_prompt_path]解析提示词{formation_prompt_path}失败. {str(e)}")
        raise e
    

def load_end_prompt():
    try:
        end_prompt_path = get_abs_path(prompts_conf["end_prompt_path"])
    except KeyError as e:
        logger.error(f"[end_prompt_path]解析提示词文件路径失败。")
        raise e
    
    try:
        return open(end_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[end_prompt_path]提示词文件{end_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[end_prompt_path]解析提示词{end_prompt_path}失败. {str(e)}")
        raise e
    
def load_revise_prompt():
    try:
        revise_prompt_path = get_abs_path(prompts_conf["revise_prompt_path"])
    except KeyError as e:
        logger.error(f"[revise_prompt_path]解析提示词文件路径失败。")
        raise e
    
    try:
        return open(revise_prompt_path, "r", encoding="utf-8").read()
    except FileNotFoundError as e:
        logger.error(f"[revise_prompt_path]提示词文件{revise_prompt_path}不存在. {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"[revise_prompt_path]解析提示词{revise_prompt_path}失败. {str(e)}")
        raise e