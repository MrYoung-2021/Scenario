"""Reusable knowledge browsing, creation, review, and deletion APIs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from rag.rag import RAG
from schemas.retrieval import KnowledgeCreate
from services.knowledge_promotion_service import content_hash
from utils.config_handler import db_conf


router = APIRouter(prefix="/api", tags=["knowledge"])
_knowledge_store: RAG | None = None
_feedback_store: RAG | None = None

KNOWLEDGE_BASES = [
    {"kb_id": "environment", "name": "环境知识库"},
    {"kb_id": "formation", "name": "编成知识库"},
    {"kb_id": "weapon", "name": "武器知识库"},
    {"kb_id": "tactics_campaign", "name": "战役级战术知识库"},
    {"kb_id": "tactics_tactical", "name": "战术级战术知识库"},
    {"kb_id": "task", "name": "任务流程知识库"},
    {"kb_id": "expert", "name": "专家知识库"},
    {"kb_id": "feedback", "name": "反馈知识库"},
]


def get_knowledge_store() -> RAG:
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = RAG()
    return _knowledge_store


def get_store(category: str) -> RAG:
    global _feedback_store
    if category != "feedback":
        return get_knowledge_store()
    if _feedback_store is None:
        _feedback_store = RAG(db_conf["feedback_collection_name"])
    return _feedback_store


@router.get("/get_knowledge_bases")
async def get_knowledge_bases() -> list[dict[str, str]]:
    return KNOWLEDGE_BASES


@router.get("/get_knowledge")
async def get_knowledge(
    kb_id: list[str] = Query(default_factory=list),
) -> list[dict]:
    knowledge: list[dict] = []
    for category in kb_id:
        knowledge.extend(get_store(category).get_texts_by_category(category))
    return knowledge


@router.post("/add_knowledge", status_code=201)
async def add_knowledge(request: KnowledgeCreate) -> dict:
    store = get_store(request.kb_id)
    digest = content_hash(request.content)
    existing = store.find_by_content_hash(digest)
    if existing:
        return {"k_id": existing["k_id"], "duplicate": True, "verified": bool(existing.get("verified", False))}
    source_id = request.source_id or digest
    ids = store.add_text(
        request.content,
        request.kb_id,
        {
            "level": request.level,
            "domain": request.domain,
            "side": request.side,
            "scenario_type": request.scenario_type,
            "source": request.source,
            "source_id": source_id,
            "verified": False,
            "content_hash": digest,
        },
    )
    return {"k_id": ids[0], "duplicate": False, "verified": False}


@router.post("/knowledge/{knowledge_id}/approve")
async def approve_knowledge(knowledge_id: str) -> dict[str, bool]:
    for category in ("feedback", "environment", "formation", "weapon", "tactics_campaign", "tactics_tactical", "task", "expert"):
        if get_store(category).set_verified(knowledge_id, True):
            return {"success": True, "verified": True}
    raise HTTPException(status_code=404, detail="知识条目不存在")


@router.delete("/delete_knowledge")
async def delete_knowledge(k_id: str) -> dict[str, bool]:
    deleted = False
    for category in ("feedback", "environment", "formation", "weapon", "tactics_campaign", "tactics_tactical", "task", "expert"):
        deleted = await get_store(category).adelete_text_by_id(k_id)
        if deleted:
            break
    return {"success": deleted}
