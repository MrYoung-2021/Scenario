import datetime
import hashlib
import os
import json
from typing import Dict, List, Optional
import numpy as np
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader, JSONLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.logger import get_logger
from models.factory import embed_model
from utils.config_handler import db_conf
from utils.path_tools import get_abs_path, get_skills_path


logger = get_logger()

class RAG:
    """RAG功能实现，用于存储和检索专业知识"""
    
    def __init__(self, collection_name=db_conf["data_collection_name"], persist_directory=get_abs_path(db_conf["directory"])):
        """初始化RAG
        """
        logger.info("初始化RAG")
        self.vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=embed_model,
            persist_directory=persist_directory,
        )
        self.embeddings = embed_model
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        
    def get_text_id(self, text: str) -> str:
        """根据标准化后的文本生成唯一 ID"""
        normalized = text.strip()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()
    def add_text(self, text: str, category: str):
        """
        添加文本到知识库
        """
        if len(text) > db_conf["chunk_size"]:
            knowledge_chunks: list[str] = self.spliter.split_text(text)
        else:
            knowledge_chunks = [text]

        metadata = {
            "category": category
        }

        ids=[self.get_text_id(text) for text in knowledge_chunks]

        self.vector_store.get
        self.vector_store.add_texts(      # 内容就加载到向量库中了
            # iterable -> list \ tuple
            knowledge_chunks,
            metadatas=[metadata for _ in knowledge_chunks],
            ids=ids
        )

        logger.info(f"文本{text}已添加到知识库")

        return ids

    async def aadd_text(self, text: str, category: str):
        """
        添加文本到知识库
        """
        if len(text) > db_conf["chunk_size"]:
            knowledge_chunks: list[str] = self.spliter.split_text(text)
        else:
            knowledge_chunks = [text]

        metadata = {
            "category": category,
        }

        ids = [self.get_text_id(text) for text in knowledge_chunks]
    
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
            include=["documents"]
        )
        if results["ids"]:
            return [
                {"k_id": id_, "kb_id": category, "content": doc}
                for id_, doc in zip(
                    results["ids"], results["documents"]
                )
            ]
        return []
    
    async def adelete_text_by_id(self, id: str) -> bool:
        """
        根据文本内容删除对应记录。
        返回 True 表示删除成功，False 表示未找到。
        """
        try:
            await self.vector_store.adelete(ids=[id])

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

    




