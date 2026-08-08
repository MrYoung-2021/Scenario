"""Application-lifetime registry for standard and LightRAG backends."""

from __future__ import annotations

import os
from pathlib import Path

from rag.lightrag_deepseek import LightRAGWrapper
from rag.rag import RAG
from services.retrieval_service import LazyLightRAGBackend, TieredRetriever
from utils.config_handler import db_conf, rag_conf


_retriever: TieredRetriever | None = None
_feedback_retriever: TieredRetriever | None = None


def _light_backend(scope: str) -> LazyLightRAGBackend:
    root = Path(__file__).resolve().parents[2]
    return LazyLightRAGBackend(
        lambda: LightRAGWrapper(
            working_dir=str(root / scope),
            api_key=os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            base_url=rag_conf["base_url"],
            llm_model=rag_conf["chat_model_name"],
            embedding_model=rag_conf["embedding_model_name"],
        )
    )


def _build(standard: RAG, *, include_lightrag: bool = True) -> TieredRetriever:
    settings = rag_conf["retrieval"]
    fallbacks = {}
    if include_lightrag:
        fallbacks = {
            scope: _light_backend(scope)
            for scope in (
                "environment",
                "red_formation",
                "blue_formation",
                "red_weapon",
                "blue_weapon",
                "red_task",
                "blue_task",
            )
        }
    return TieredRetriever(
        standard,
        fallbacks,
        score_threshold=float(settings["score_threshold"]),
        standard_top_k=int(settings["standard_top_k"]),
        lightrag_top_k=int(settings["lightrag_top_k"]),
        minimum_verified_hits=int(settings["minimum_verified_hits"]),
    )


def get_tiered_retriever() -> TieredRetriever:
    global _retriever
    if _retriever is None:
        _retriever = _build(RAG())
    return _retriever


def get_feedback_retriever() -> TieredRetriever:
    global _feedback_retriever
    if _feedback_retriever is None:
        _feedback_retriever = _build(
            RAG(db_conf["feedback_collection_name"]),
            include_lightrag=False,
        )
    return _feedback_retriever
