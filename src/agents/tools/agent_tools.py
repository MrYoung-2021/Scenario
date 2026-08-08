"""Knowledge tools backed by standard-first tiered retrieval."""

import json

from langchain_core.tools import tool

from schemas.retrieval import RetrievalQuery
from services.retrieval_registry import get_feedback_retriever, get_tiered_retriever
from utils.logger import get_logger


logger = get_logger()


async def _search(
    query: str,
    category: str,
    *,
    side: str | None = None,
    level: str | None = None,
    feedback: bool = False,
) -> str:
    retriever = get_feedback_retriever() if feedback else get_tiered_retriever()
    result = await retriever.retrieve(
        RetrievalQuery(query=query, category=category, side=side, level=level)
    )
    logger.info(
        "知识检索 category=%s side=%s fallback=%s reason=%s",
        category,
        side,
        result.used_fallback,
        result.fallback_reason,
    )
    return json.dumps(result.model_dump(), ensure_ascii=False)


@tool(description="从军事想定地理和气象知识库中检索相关资料")
async def search_environment_KB(query: str) -> str:
    return await _search(query, "environment")


@tool(description="从红方军事想定兵力与编成部署知识库中检索相关资料")
async def search_red_formation_KB(query: str) -> str:
    return await _search(query, "formation", side="red")


@tool(description="从蓝方军事想定兵力与编成部署知识库中检索相关资料")
async def search_blue_formation_KB(query: str) -> str:
    return await _search(query, "formation", side="blue")


@tool(description="从红方军事想定兵器运用与战术知识库中检索相关资料")
async def search_red_weapon_KB(query: str) -> str:
    return await _search(query, "weapon", side="red")


@tool(description="从蓝方军事想定兵器运用与战术知识库中检索相关资料")
async def search_blue_weapon_KB(query: str) -> str:
    return await _search(query, "weapon", side="blue")


@tool(description="从红方任务规划与流程约束库中检索相关资料")
async def search_red_task_KB(query: str) -> str:
    return await _search(query, "task", side="red")


@tool(description="从蓝方任务规划与流程约束库中检索相关资料")
async def search_blue_task_KB(query: str) -> str:
    return await _search(query, "task", side="blue")


@tool(description="从红蓝双方任务规划与流程约束库中检索相关资料")
async def search_task_KB(query: str) -> str:
    return await _search(query, "task", side="all")


@tool(description="从已审核专家知识库中检索相关资料")
async def search_expert_KB(query: str) -> str:
    return await _search(query, "expert")


@tool(description="从经验与反馈知识库中检索相关资料")
async def search_experience_KB(query: str) -> str:
    return await _search(query, "feedback", feedback=True)
