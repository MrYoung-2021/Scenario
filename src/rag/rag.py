import datetime
import os
import json
import numpy as np
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader, JSONLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.logger import get_logger
from models.factory import embed_model
from utils.config_handler import chroma_conf
from utils.path_tools import get_abs_path, get_skills_path

from langchain_classic.indexes import SQLRecordManager, index

logger = get_logger()

class RAG:
    """RAG功能实现，用于存储和检索专业知识"""
    
    def __init__(self, collection_name=chroma_conf["data_collection_name"]):
        """初始化RAG
        """
        logger.info("初始化RAG")
        self.vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=embed_model,
            persist_directory=get_abs_path(chroma_conf["persist_directory"]),
        )
        self.embeddings = embed_model
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        self.record_manager = SQLRecordManager(
            namespace="chroma/docs",
            db_url=f"sqlite:///{get_abs_path(chroma_conf["langchain_indexing"])}"
        )
        self.record_manager.create_schema()
        
    def add_text(self, text: str, src: str):
        """
        添加文本到知识库
        """
        if len(text) > chroma_conf["chunk_size"]:
            knowledge_chunks: list[str] = self.spliter.split_text(text)
        else:
            knowledge_chunks = [text]

        metadata = {
            "source": src,
            "create_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    
        self.vector_store.add_texts(      # 内容就加载到向量库中了
            # iterable -> list \ tuple
            knowledge_chunks,
            metadatas=[metadata for _ in knowledge_chunks],
        )

        logger.info(f"文本{src}已添加到知识库")

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
            
            # 添加到向量存储
            # self.vector_store.add_documents(split_docs)
            result = index(
                docs_source=split_docs,
                record_manager=self.record_manager,
                vector_store=self.vector_store,
                cleanup="incremental",
                source_id_key="source"
            )
            
            logger.info(f"文档添加成功: {file_path}\n索引结果为：{result}")
        except Exception as e:
            logger.error(f"添加文档失败: {e}", exc_info=True)
    
    def save_snapshot(self, snapshot, snapshot_file):
        """将快照保存到文件（JSON格式）"""
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

    def load_snapshot(self, snapshot_file):
        """从文件加载快照"""
        if not os.path.exists(snapshot_file):
            with open(snapshot_file, 'w') as f:
                json.dump({}, f, indent=2)
                return {}

        with open(snapshot_file, 'r', encoding='utf-8') as f:
            return json.load(f)
        
    def check_snapshot(self, snapshot, file_path):
        """检查快照是否更新"""
        stat_size = os.path.getsize(file_path)
        stat_time = os.path.getmtime(file_path)
        
        if file_path not in snapshot or snapshot[file_path] != [stat_size, stat_time]:
            print("="*20)
            snapshot[file_path] = (stat_size, stat_time)
            return True
        
        return False

    def add_skill_documents(self, skills_path=get_skills_path("")):
        """添加Skills目录下的所有文档到知识库
        
        Args:
            skills_path: Skills目录路径
        """
        try:
            logger.info(f"开始添加Skills目录下的文档: {skills_path}")

            snapshot_path = get_abs_path(chroma_conf["snapshot_path"])

            snapshot = self.load_snapshot(snapshot_path)
            
            # 遍历Skills目录下的所有文件
            for root, dirs, files in os.walk(skills_path):
                if os.path.basename(root) == 'references':
                    for file in files:
                        if file.endswith(('.md', '.txt', '.json')):
                            file_path = os.path.join(root, file)
                            if self.check_snapshot(snapshot, file_path):
                                self.add_document(file_path)
            
            self.save_snapshot(snapshot, snapshot_path)

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
    

# 示例用法
if __name__ == "__main__":
    rag = RAG()
    
    # 添加Skills文档
    path = get_skills_path()

    rag.add_skill_documents(path)
    
    # 测试查询
    results = rag.query("陆战想定生成规则")
    print("查询结果:")
    for i, result in enumerate(results):
        print(f"{i+1}. 来源: {result['source']}")
        print(f"   内容: {result['content'][:100]}...")
        print()




