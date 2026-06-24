import functools
import os
import asyncio
from typing import List, Optional, Union
from pathlib import Path

from lightrag import LightRAG as BaseLightRAG, QueryParam
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed, openai_complete
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.utils import setup_logger, wrap_embedding_func_with_attrs
import numpy as np
from openai import AsyncOpenAI

from utils.config_handler import rag_conf
from models.factory import embed_model as qwen_embed


llm_kwargs = {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", 
    "api_key": os.environ.get("OPENAI_API_KEY")
}

embedding_kwargs = {
    # "model": rag_conf["embedding_model_name"],
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", 
    "api_key": os.environ.get("OPENAI_API_KEY")
}


class LightRAGWrapper:
    """
    LightRAG 封装类，简化初始化和常用操作

    """
    
    def __init__(
        self,
        working_dir: str,
        llm_model_func=None,
        embedding_func=None,
        auto_init: bool = True,
        log_level: str = "INFO"
    ):
        """
        初始化 LightRAG 封装类
        
        Args:
            working_dir: 工作目录，用于存储索引和缓存数据
            llm_model_func: LLM 调用函数，默认使用 gpt-4o-mini
            embedding_func: Embedding 函数，默认使用 OpenAI embedding
            auto_init: 是否自动初始化存储（建议设为 True）
            log_level: 日志级别（DEBUG/INFO/WARN/ERROR）
        """
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        
        # 配置日志
        setup_logger("lightrag", level=log_level)
        
        # 设置默认函数
        self.llm_model_func = llm_model_func or openai_complete
        self.embedding_func = embedding_func or self.qwen_embedding
        
        # 初始化底层 RAG 实例
        self._rag = BaseLightRAG(
            working_dir=str(self.working_dir),
            llm_model_func=self.llm_model_func,
            llm_model_name=rag_conf["chat_model_name"],
            llm_model_kwargs=llm_kwargs,
            embedding_func=self.embedding_func,
        )
        
        self._initialized = False
        
        if auto_init:
            self._init_storages()

    # ------- 自定义 Embedding 函数（维度和 token 数）-------
    @wrap_embedding_func_with_attrs(
        embedding_dim=1024,          # 千问 text-embedding-v2 向量维度
        max_token_size=2048          # 千问 embedding 最大 token 数
    )
    async def qwen_embedding(texts: list[str]) -> np.ndarray:
        client = AsyncOpenAI(
            api_key=os.environ["DASHSCOPE_API_KEY"],
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        resp = await client.embeddings.create(
            model=rag_conf["embedding_model_name"],
            input=texts,
        )
        return np.array([d.embedding for d in resp.data])
    
    def _init_storages(self):
        """初始化存储后端（同步包装）"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已有事件循环，创建新任务
                import nest_asyncio
                nest_asyncio.apply()
                asyncio.create_task(self._async_init())
            else:
                asyncio.run(self._async_init())
        except RuntimeError:
            # 没有事件循环，直接运行
            asyncio.run(self._async_init())
    
    async def _async_init(self):
        """异步初始化存储后端"""
        await self._rag.initialize_storages()
        await initialize_pipeline_status()
        self._initialized = True
    
    async def _ensure_initialized(self):
        """确保存储已初始化"""
        if not self._initialized:
            await self._async_init()
    
    # ==================== 文档插入方法 ====================
    
    def insert(self, content: Union[str, List[str]]):
        """
        插入文档（同步方法）
        
        Args:
            content: 单个文本字符串或文本列表
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                asyncio.create_task(self._async_insert(content))
            else:
                asyncio.run(self._async_insert(content))
        except RuntimeError:
            asyncio.run(self._async_insert(content))
    
    async def ainsert(self, content: Union[str, List[str]]):
        """
        异步插入文档
        
        Args:
            content: 单个文本字符串或文本列表
        """
        await self._ensure_initialized()
        
        if isinstance(content, str):
            await self._rag.ainsert(content)
        else:
            await self._rag.ainsert(content)
    
    async def _async_insert(self, content: Union[str, List[str]]):
        """内部异步插入实现"""
        await self._ensure_initialized()
        
        if isinstance(content, str):
            await self._rag.ainsert(content)
        else:
            await self._rag.ainsert(content)
    
    # ==================== 查询方法 ====================
    
    def query(
        self,
        question: str,
        mode: str = "hybrid",
        top_k: int = 60,
        only_need_context: bool = False,
        **kwargs
    ) -> str:
        """
        查询（同步方法）
        
        Args:
            question: 用户问题
            mode: 查询模式
                - "naive": 仅向量检索，不使用知识图谱
                - "local": 本地检索，聚焦具体实体
                - "global": 全局检索，聚焦主题和关系
                - "hybrid": 混合检索（推荐），结合 local + global
                - "mix": 融合检索，结合知识图谱和向量
                - "bypass": 直接调用 LLM，不检索
            top_k: 返回结果数量（实体或关系数）
            only_need_context: 是否只返回上下文而不生成答案
            **kwargs: 其他 QueryParam 参数，如：
                - max_token_for_text_unit: chunk token 限制
                - max_token_for_global_context: 关系描述 token 限制
                - max_token_for_local_context: 实体描述 token 限制
                - enable_rerank: 是否启用重排序
                - stream: 是否流式输出
        
        Returns:
            LLM 生成的答案文本
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                future = asyncio.ensure_future(
                    self._async_query(question, mode, top_k, only_need_context, **kwargs)
                )
                return self._run_async_in_sync(future)
            else:
                return asyncio.run(
                    self._async_query(question, mode, top_k, only_need_context, **kwargs)
                )
        except RuntimeError:
            return asyncio.run(
                self._async_query(question, mode, top_k, only_need_context, **kwargs)
            )
    
    async def aquery(
        self,
        question: str,
        mode: str = "hybrid",
        top_k: int = 60,
        only_need_context: bool = False,
        **kwargs
    ) -> str:
        """
        异步查询
        
        Args:
            question: 用户问题
            mode: 查询模式
            top_k: 返回结果数量
            only_need_context: 是否只返回上下文
            **kwargs: 其他 QueryParam 参数
        
        Returns:
            LLM 生成的答案文本
        """
        await self._ensure_initialized()
        
        param = QueryParam(
            mode=mode,
            top_k=top_k,
            only_need_context=only_need_context,
            **kwargs
        )
        
        return await self._rag.aquery(question, param=param)
    
    async def _async_query(self, question: str, mode: str, top_k: int, only_need_context: bool, **kwargs) -> str:
        """内部异步查询实现"""
        await self._ensure_initialized()
        
        param = QueryParam(
            mode=mode,
            top_k=top_k,
            only_need_context=only_need_context,
            **kwargs
        )
        
        return await self._rag.aquery(question, param=param)
    
    def _run_async_in_sync(self, coro):
        """
        在同步环境中运行异步协程
        处理嵌套事件循环的情况
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 嵌套循环：使用 nest_asyncio
                try:
                    import nest_asyncio
                    nest_asyncio.apply()
                except ImportError:
                    raise RuntimeError(
                        "Nested asyncio detected. Please install nest_asyncio: "
                        "pip install nest_asyncio"
                    )
                return loop.run_until_complete(coro)
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # 没有事件循环
            return asyncio.run(coro)
    
    # ==================== 便捷方法 ====================
    
    def search(self, question: str, top_k: int = 20, mode: str = "hybrid") -> str:
        """
        简化的搜索方法，默认使用推荐参数
        
        Args:
            question: 用户问题
            top_k: 检索数量
            mode: 查询模式
        
        Returns:
            答案文本
        """
        return self.query(question, mode=mode, top_k=top_k)
    
    def get_context(self, question: str, mode: str = "hybrid", top_k: int = 60) -> str:
        """
        仅获取检索上下文，不生成答案
        
        Args:
            question: 用户问题
            mode: 查询模式
            top_k: 检索数量
        
        Returns:
            检索到的上下文文本
        """
        return self.query(question, mode=mode, top_k=top_k, only_need_context=True)
    
    def cleanup(self):
        """清理资源"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._rag.finalize_storages())
            else:
                asyncio.run(self._rag.finalize_storages())
        except Exception as e:
            print(f"Cleanup warning: {e}")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.cleanup()
    
    # ==================== 信息方法 ====================
    
    def get_working_dir(self) -> str:
        """获取工作目录"""
        return str(self.working_dir)
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized


# ==================== 使用示例 ====================

def example_basic_usage():
    """基础使用示例"""
    # 初始化（自动创建工作目录和存储）
    rag = LightRAGWrapper(working_dir="./my_rag_storage")
    
    # 插入单个文档
    rag.insert("北京是中国的首都，是一座历史悠久的城市。它成功举办了2008年夏季奥运会。")
    
    # 执行查询
    result = rag.query("北京有哪些城市名片？", mode="hybrid", top_k=10, only_need_context=True)
    print(f"Query result: {result}")
    
    # 使用上下文管理器自动清理
    # with LightRAGWrapper(working_dir="./another_rag") as rag2:
    #     rag2.insert("人工智能正在改变世界。深度学习是AI的重要分支。")
    #     result2 = rag2.search("什么是深度学习？", top_k=5)
    #     print(f"Search result: {result2}")


async def example_async_usage():
    """异步使用示例"""
    rag = LightRAGWrapper(working_dir="./async_rag_storage", auto_init=False)
    await rag._async_init()
    
    # 批量插入
    texts = [
        "机器学习是人工智能的一个子领域。",
        "神经网络受到生物大脑的启发。",
        "强化学习通过奖励机制来训练模型。"
    ]
    await rag.ainsert(texts)
    
    # 异步查询
    result = await rag.aquery("机器学习有哪些相关技术？", mode="hybrid", top_k=10)
    print(f"Async result: {result}")
    
    await rag._rag.finalize_storages()


def example_batch_insert():
    """批量插入示例"""
    rag = LightRAGWrapper(working_dir="./batch_rag")
    
    documents = [
        "Python是一种高级编程语言，以简洁易读著称。",
        "JavaScript主要用于前端Web开发。",
        "Rust语言注重内存安全和高性能。"
    ]
    
    rag.insert(documents)
    result = rag.query("有哪些编程语言？各自有什么特点？", mode="global")
    print(result)


def example_context_only():
    """仅获取上下文示例"""
    rag = LightRAGWrapper(working_dir="./context_rag")
    
    rag.insert("""
    量子计算利用量子力学原理进行计算。
    量子比特可以同时处于0和1的叠加态。
    量子霸权指量子计算机解决经典计算机无法完成的任务。
    """)
    
    # 只获取检索到的上下文，不生成答案
    context = rag.get_context("什么是量子计算？", mode="local")
    print(f"Retrieved context:\n{context}")


if __name__ == "__main__":
    # 运行示例
    print("=== Basic Usage Example ===")
    example_basic_usage()
    
    # print("\n=== Batch Insert Example ===")
    # example_batch_insert()
    
    # print("\n=== Context Only Example ===")
    # example_context_only()
    
    # 异步示例需要单独运行
    # asyncio.run(example_async_usage())