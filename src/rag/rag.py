import hashlib
import os
from datetime import datetime, timezone
from typing import Any
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader, JSONLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.logger import get_logger
from models.factory import embed_model
from utils.config_handler import db_conf, rag_conf
from utils.path_tools import get_abs_path, get_skills_path
from schemas.retrieval import RetrievedItem

_VALID_CATEGORIES = {
    "environment", "formation", "weapon", "tactics_campaign", "tactics_tactical", "task", "expert", "feedback"
}


logger = get_logger()

class RAG:
    """RAG功能实现，用于存储和检索专业知识"""
    
    def __init__(self, collection_name=db_conf["data_collection_name"], persist_directory=get_abs_path(db_conf["directory"]), *, vector_store=None, embeddings=None):
        """初始化RAG
        """
        logger.info("初始化RAG")
        self.vector_store = vector_store or Chroma(
            collection_name=collection_name,
            embedding_function=embeddings or embed_model,
            persist_directory=persist_directory,
        )
        self.embeddings = embeddings or embed_model
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        
    def get_text_id(self, text: str, category: str = "") -> str:
        """根据知识库和标准化后的文本生成唯一 ID。"""
        normalized = f"{category}\0{text.strip()}"
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def _deduplication_settings(self) -> tuple[bool, float]:
        settings = rag_conf.get("knowledge_deduplication", {}) if isinstance(rag_conf, dict) else {}
        enabled = bool(settings.get("enabled", True))
        try:
            threshold = float(settings.get("threshold", 0.95))
        except (TypeError, ValueError):
            threshold = 0.95
        return enabled, min(1.0, max(0.0, threshold))

    def _find_similar(self, text: str, category: str) -> dict[str, Any] | None:
        enabled, threshold = self._deduplication_settings()
        if not enabled or not hasattr(self.vector_store, "similarity_search_with_relevance_scores"):
            return None
        try:
            try:
                pairs = self.vector_store.similarity_search_with_relevance_scores(text, k=1, filter={"category": category})
            except TypeError:
                pairs = self.vector_store.similarity_search_with_relevance_scores(text, k=1, where={"category": category})
            if not pairs:
                return None
            document, score = pairs[0]
            score = float(score)
            if score < threshold:
                return None
            metadata = dict(getattr(document, "metadata", {}) or {})
            return {"score": score, "content": str(getattr(document, "page_content", "")), "k_id": metadata.get("k_id") or metadata.get("id")}
        except Exception:
            logger.warning("相似度去重检查失败", exc_info=True)
            return None

    async def _find_similar_async(self, text: str, category: str) -> dict[str, Any] | None:
        enabled, threshold = self._deduplication_settings()
        if not enabled or not hasattr(self.vector_store, "asimilarity_search_with_relevance_scores"):
            return None
        try:
            try:
                pairs = await self.vector_store.asimilarity_search_with_relevance_scores(text, k=1, filter={"category": category})
            except TypeError:
                pairs = await self.vector_store.asimilarity_search_with_relevance_scores(text, k=1, where={"category": category})
            if not pairs:
                return None
            document, score = pairs[0]
            score = float(score)
            if score < threshold:
                return None
            metadata = dict(getattr(document, "metadata", {}) or {})
            return {"score": score, "content": str(getattr(document, "page_content", "")), "k_id": metadata.get("k_id") or metadata.get("id")}
        except Exception:
            logger.warning("相似度去重检查失败", exc_info=True)
            return None

    def add_text(self, text: str, category: str, metadata: dict[str, Any] | None = None):
        """
        添加文本到知识库
        """
        if len(text) > db_conf["chunk_size"]:
            knowledge_chunks: list[str] = self.text_splitter.split_text(text)
        else:
            knowledge_chunks = [text]

        caller_metadata = metadata
        metadata = {"category": category, **(metadata or {})}
        similar = self._find_similar(text, category)
        if similar:
            metadata.update({"similarity_warning": True, "similarity_score": similar["score"], "similar_content": similar["content"], "similar_k_id": similar.get("k_id") or ""})
        metadata.setdefault("level", "general")
        metadata.setdefault("domain", "general")
        metadata.setdefault("side", "all")
        metadata.setdefault("scenario_type", "all")
        metadata.setdefault("source", "manual")
        metadata.setdefault("source_id", "")
        metadata.setdefault("verified", False)
        metadata.setdefault("content_hash", "")
        metadata.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        metadata.setdefault("version", 1)
        if caller_metadata is not None:
            caller_metadata.update(metadata)

        ids = [self.get_text_id(chunk, category) for chunk in knowledge_chunks]

        self.vector_store.add_texts(      # 内容就加载到向量库中了
            # iterable -> list \ tuple
            knowledge_chunks,
            metadatas=[metadata for _ in knowledge_chunks],
            ids=ids
        )

        logger.info(f"文本{text}已添加到知识库")

        return ids

    async def aadd_text(self, text: str, category: str, metadata: dict[str, Any] | None = None):
        """
        添加文本到知识库
        """
        if len(text) > db_conf["chunk_size"]:
            knowledge_chunks: list[str] = self.text_splitter.split_text(text)
        else:
            knowledge_chunks = [text]

        caller_metadata = metadata
        metadata = {"category": category, **(metadata or {})}
        similar = await self._find_similar_async(text, category)
        if similar:
            metadata.update({"similarity_warning": True, "similarity_score": similar["score"], "similar_content": similar["content"], "similar_k_id": similar.get("k_id") or ""})
        metadata.setdefault("level", "general")
        metadata.setdefault("domain", "general")
        metadata.setdefault("side", "all")
        metadata.setdefault("scenario_type", "all")
        metadata.setdefault("source", "manual")
        metadata.setdefault("source_id", "")
        metadata.setdefault("verified", False)
        metadata.setdefault("content_hash", "")
        metadata.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        metadata.setdefault("version", 1)
        if caller_metadata is not None:
            caller_metadata.update(metadata)

        ids = [self.get_text_id(chunk, category) for chunk in knowledge_chunks]
    
        await self.vector_store.aadd_texts(      # 内容就加载到向量库中了
            # iterable -> list \ tuple
            knowledge_chunks,
            metadatas=[metadata for _ in knowledge_chunks],
            ids=ids
        )

        logger.info(f"文本{text}已添加到知识库")

        return ids

    def add_document(self, file_path):
        """添加文档到知识库
        
        Args:
            file_path: 文档路径
        """
        try:
            logger.info(f"添加文档: {file_path}")
            # 根据文件类型选择加载器
            if file_path.endswith('.md') or file_path.endswith('.txt'):
                loader = TextLoader(file_path, encoding='utf-8')
            elif file_path.endswith('.json'):
                loader = JSONLoader(
                    file_path=file_path,
                    jq_schema='.',
                    text_content=False
                )
            else:
                logger.warning(f"不支持的文件类型: {file_path}")
                return
            
            # 加载文档
            documents = loader.load()
            # 分割文档
            split_docs = self.text_splitter.split_documents(documents)
            logger.info(f"文档分割完成，生成{len(split_docs)}个文档块")
                        
        except Exception as e:
            logger.error(f"添加文档失败: {e}", exc_info=True)



    def add_skill_documents(self, skills_path=get_skills_path("")):
        """添加Skills目录下的所有文档到知识库
        
        Args:
            skills_path: Skills目录路径
        """
        try:
            logger.info(f"开始添加Skills目录下的文档: {skills_path}")
            
            # 遍历Skills目录下的所有文件
            for root, dirs, files in os.walk(skills_path):
                if os.path.basename(root) == 'references':
                    for file in files:
                        if file.endswith(('.md', '.txt', '.json')):
                            file_path = os.path.join(root, file)
                            self.add_document(file_path)
            
            logger.info("Skills文档添加完成")
        except Exception as e:
            logger.error(f"添加Skills文档失败: {e}", exc_info=True)
    
    def query(self, query, k=3):
        """查询知识库
        
        Args:
            query: 查询文本
            k: 返回结果数量
            
        Returns:
            相关文档列表
        """
        try:
            logger.info(f"查询知识库: {query[:20]}..., 限制返回{ k }条结果")
            if not self.vector_store:
                logger.warning("知识库为空，请先添加文档")
                return []
            
            # 相似度搜索
            results = self.vector_store.similarity_search(query, k=k)

            # 格式化结果
            # formatted_results = []
            # for i, result in enumerate(results):
            #     formatted_results.append({
            #         "content": result.page_content,
            #         "source": result.metadata.get("source", "unknown"),
            #         "score": 1.0  # 返回分数，待计算
            #     })
            
            logger.info(f"查询完成，返回{len(results)}条结果")
            # return formatted_results
            return results
        except Exception as e:
            logger.error(f"查询失败: {e}", exc_info=True)
            return []

    async def asearch(
        self,
        query: str,
        *,
        k: int = 3,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievedItem]:
        """Return serializable scored items for tiered retrieval."""
        if not self.vector_store:
            return []
        where = self._where_filter(metadata_filter or {})
        try:
            pairs = await self.vector_store.asimilarity_search_with_relevance_scores(
                query, k=k, filter=where
            )
        except TypeError:
            pairs = await self.vector_store.asimilarity_search_with_relevance_scores(query, k=k, where=where)
        items: list[RetrievedItem] = []
        for document, score in pairs:
            metadata = dict(document.metadata or {})
            category = metadata.get("category", "expert")
            if category == "tactics":
                category = "tactics_tactical"
            elif category not in _VALID_CATEGORIES:
                category = "expert"
            items.append(
                RetrievedItem(
                    content=document.page_content,
                    backend="standard",
                    category=category,
                    score=float(score),
                    source=str(metadata.get("source", "standard")),
                    source_id=str(metadata.get("source_id") or metadata.get("id") or ""),
                    verified=bool(metadata.get("verified", False)),
                    metadata=metadata,
                )
            )
        return items

    @staticmethod
    def _where_filter(filters: dict[str, Any]) -> dict[str, Any] | None:
        filters = {key: value for key, value in filters.items() if value is not None}
        if not filters:
            return None
        clauses = []
        for key, value in filters.items():
            if key == "side" and value != "all":
                clauses.append({"$or": [{"side": value}, {"side": "all"}]})
            else:
                clauses.append({key: value})
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}
        
    async def aquery(self, query, k=3):
        """查询知识库
        
        Args:
            query: 查询文本
            k: 返回结果数量
            
        Returns:
            相关文档列表
        """
        try:
            logger.info(f"查询知识库: {query[:20]}..., 限制返回{ k }条结果")
            if not self.vector_store:
                logger.warning("知识库为空，请先添加文档")
                return []
            
            # 相似度搜索
            results = await self.vector_store.asimilarity_search(query, k=k)
                        
            # 格式化结果
            # formatted_results = []
            # for i, result in enumerate(results):
            #     formatted_results.append({
            #         "content": result.page_content,
            #         "source": result.metadata.get("source", "unknown"),
            #         "score": 1.0  # 返回分数，待计算
            #     })
            
            logger.info(f"查询完成，返回{len(results)}条结果")
            # return formatted_results
            return results
        except Exception as e:
            logger.error(f"查询失败: {e}", exc_info=True)
            return []
    
    def get_relevant_knowledge(self, query):
        """获取与想定类型相关的知识
        
        Args:
            scenario_type: 想定类型（如"陆战"、"海战"等）
            
        Returns:
            相关知识列表
        """
        logger.info(f"获取与{query[:20]}...相关的知识")
        # query = f"{scenario_type}想定生成规则和示例"
        results = self.query(query, k=3)
        logger.info(f"获取到{len(results)}条相关知识")
        return results
    
    def get_texts_by_category(self, category: str):
        """
        根据类别获取所有文本，返回字典列表，包含 id、文本。
        """
        results = self.vector_store.get(
            where={"category": category},
            include=["documents", "metadatas"]
        )
        if results["ids"]:
            return [
                {"k_id": id_, "kb_id": category, "content": doc, **(metadata or {})}
                for id_, doc, metadata in zip(
                    results["ids"], results["documents"], results.get("metadatas", [])
                )
            ]
        return []

    def find_by_content_hash(self, value: str, category: str | None = None) -> dict | None:
        where: dict[str, Any] = {"content_hash": value}
        if category is not None:
            where = {"$and": [{"content_hash": value}, {"category": category}]}
        results = self.vector_store.get(where=where, include=["documents", "metadatas"])
        if not results.get("ids"):
            return None
        return {"k_id": results["ids"][0], "content": results.get("documents", [""])[0], **(results.get("metadatas", [{}])[0] or {})}

    def set_verified(self, knowledge_id: str, verified: bool) -> bool:
        results = self.vector_store.get(ids=[knowledge_id], include=["documents", "metadatas"])
        if not results.get("ids"):
            return False
        metadata = dict((results.get("metadatas") or [{}])[0] or {})
        metadata["verified"] = verified
        from langchain_core.documents import Document
        self.vector_store.update_documents(
            [knowledge_id],
            [Document(page_content=(results.get("documents") or [""])[0], metadata=metadata)],
        )
        return True
    
    async def adelete_text_by_id(self, id: str) -> bool:
        """
        根据文本内容删除对应记录。
        返回 True 表示删除成功，False 表示未找到。
        """
        try:
            before = self.vector_store.get(ids=[id], include=["metadatas"])
            if not before.get("ids"):
                return False
            await self.vector_store.adelete(ids=[id])
            after = self.vector_store.get(ids=[id], include=["metadatas"])
            if after.get("ids"):
                logger.error("删除后条目仍然存在: %s", id)
                return False

        except Exception as e:
            logger.error(f"删除失败: {e}", exc_info=True)
            return False
        
        return True

    

# 示例用法
if __name__ == "__main__":
    rag = RAG()
    
    rag.add_text("这是一个测试文本", "environment")
    rag.add_text("这是一个测试文本", "formation")
    rag.add_text("这是一个测试文本", "weapon")
    rag.add_text("这是一个测试文本", "tactics")
    rag.add_text("这是一个测试文本", "task")
    rag.add_text("这是一个测试文本", "other")

    print(rag.get_texts_by_category("other"))

    




