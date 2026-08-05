import os
from langchain_core.tools import tool
from langgraph.prebuilt.tool_node import ToolCallRequest


from utils.path_tools import get_abs_path
from utils.prompt_loader import load_summary_prompt
from utils.config_handler import rag_conf, db_conf
from rag.rag import RAG
from utils.logger import get_logger

logger = get_logger()

from rag.lightrag_deepseek import LightRAGWrapper


@tool(description="从军事想定地理和气象知识库中检索相关资料")
async def search_environment_KB(query: str) -> str:
    wrapper = LightRAGWrapper(
        working_dir="./environment",
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=rag_conf["base_url"],
        llm_model=rag_conf["chat_model_name"],
        embedding_model=rag_conf["embedding_model_name"],
    )
    logger.info("调用search_environment_KB工具")
    return await wrapper.aquery(query, only_need_context=True)

@tool(description="从红方军事想定兵力与编成部署知识库中检索相关资料")
async def search_red_formation_KB(query: str) -> str:
    wrapper = LightRAGWrapper(
        working_dir="./red_formation",
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=rag_conf["base_url"],
        llm_model=rag_conf["chat_model_name"],
        embedding_model=rag_conf["embedding_model_name"],
    )
    logger.info("调用search_red_formation_KB工具")
    return await wrapper.aquery(query, only_need_context=True)

@tool(description="从蓝方军事想定兵力与编成部署知识库中检索相关资料")
async def search_blue_formation_KB(query: str) -> str:
    wrapper = LightRAGWrapper(
        working_dir="./blue_formation",
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=rag_conf["base_url"],
        llm_model=rag_conf["chat_model_name"],
        embedding_model=rag_conf["embedding_model_name"],
    )
    logger.info("调用search_blue_formation_KB工具")
    return await wrapper.aquery(query, only_need_context=True)

@tool(description="从红方军事想定兵器运用与战术知识库中检索相关资料")
async def search_red_weapon_KB(query: str) -> str:
    wrapper = LightRAGWrapper(
        working_dir="./red_weapon",
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=rag_conf["base_url"],
        llm_model=rag_conf["chat_model_name"],
        embedding_model=rag_conf["embedding_model_name"],
    )
    logger.info("调用search_red_weapon_KB工具")
    return await wrapper.aquery(query, only_need_context=True)

@tool(description="从蓝方军事想定兵器运用与战术知识库中检索相关资料")
async def search_blue_weapon_KB(query: str) -> str:
    wrapper = LightRAGWrapper(
        working_dir="./blue_weapon",
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=rag_conf["base_url"],
        llm_model=rag_conf["chat_model_name"],
        embedding_model=rag_conf["embedding_model_name"],
    )
    logger.info("调用search_blue_weapon_KB工具")
    return await wrapper.aquery(query, only_need_context=True)

@tool(description="从红方任务规划与流程约束库中检索相关资料")
async def search_red_task_KB(query: str) -> str:
    wrapper = LightRAGWrapper(
        working_dir="./red_task",
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=rag_conf["base_url"],
        llm_model=rag_conf["chat_model_name"],
        embedding_model=rag_conf["embedding_model_name"],
    )
    return await wrapper.aquery(query, only_need_context=True)

@tool(description="从蓝方任务规划与流程约束库中检索相关资料")
async def search_blue_task_KB(query: str) -> str:
    wrapper = LightRAGWrapper(
        working_dir="./blue_task",
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=rag_conf["base_url"],
        llm_model=rag_conf["chat_model_name"],
        embedding_model=rag_conf["embedding_model_name"],
    )
    logger.info("调用search_blue_task_KB工具")
    return await wrapper.aquery(query, only_need_context=True)

@tool(description="从任务规划与流程约束库中检索相关资料")
async def search_task_KB(query: str) -> str:
    wrapper = LightRAGWrapper(
        working_dir="./red_task",
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=rag_conf["base_url"],
        llm_model=rag_conf["chat_model_name"],
        embedding_model=rag_conf["embedding_model_name"],
    )
    logger.info("调用search_task_KB工具")
    return await wrapper.aquery(query, only_need_context=True)

@tool(description="从专家知识库中检索相关资料")
async def search_expert_KB(query: str) -> str:
    rag = RAG()
    logger.info("调用search_expert_KB工具")
    # return "暂无相关资料"
    return await rag.aquery(query)

@tool(description="从经验知识库中检索相关资料")
async def search_experience_KB(query: str) -> str:
    rag = RAG(db_conf["feedback_collection_name"])
    logger.info("调用search_experience_KB工具")
    # return "暂无相关资料"
    return await rag.aquery(query)