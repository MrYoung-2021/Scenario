import asyncio
import logging
import os
import time
import warnings
from pathlib import Path
from typing import List, Optional, Union

# ---------------------------------------------------------------------------
# LightRAG core imports
# ---------------------------------------------------------------------------
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed, openai_complete
from lightrag.utils import EmbeddingFunc
from lightrag.utils import wrap_embedding_func_with_attrs

import pdfplumber
import numpy as np
from openai import AsyncOpenAI


from utils.config_handler import rag_conf


# ============================================================================
# LightRAG 封装类
# ============================================================================
class LightRAGWrapper:
    """LightRAG 功能封装，支持 **字符串**、**Markdown 文件 (.md)** 和 **PDF 文件 (.pdf)** 输入。"""

    def __init__(
        self,
        working_dir: str,
        api_key: str,
        base_url: str,
        llm_model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
        embedding_dim: int = 1536,
        max_embed_tokens: int = 8192,
    ):
        """
        Parameters
        ----------
        working_dir : str
            LightRAG 文件后端的工作目录。
        api_key : str
            LLM 和嵌入模型的 API 密钥。
        base_url : str
            OpenAI 兼容 API 的基础 URL。
        llm_model : str
            LLM 模型名称（默认 ``gpt-4o-mini``）。
        embedding_model : str
            嵌入模型名称（默认 ``text-embedding-3-small``）。
        embedding_dim : int
            嵌入向量维度（默认 1536，匹配 text-embedding-3-small）。
        max_embed_tokens : int
            单次嵌入调用最大 token 数。
        **lightrag_kwargs
            传递给 ``LightRAG`` 的其它关键字参数。
        """
        self.working_dir = working_dir
        self.api_key = api_key
        self.base_url = base_url
        self.llm_model = llm_model
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self.max_embed_tokens = max_embed_tokens
        self.llm_kwargs = {
            "base_url": base_url, 
            "api_key": api_key
        }

        # 创建 working_dir（如果不存在）
        Path(self.working_dir).mkdir(parents=True, exist_ok=True)


        # 实例化 LightRAG
        # self.rag = LightRAG(
        #     working_dir=self.working_dir,
        #     llm_model_func=openai_complete_if_cache(
        #         api_key=self.api_key,
        #         base_url=self.base_url,
        #         model=self.llm_model,
        #     ),
        #     embedding_func=openai_embed(
        #         api_key=self.api_key,
        #         base_url=self.base_url,
        #         model=self.embedding_model,
        #         dimensions=self.embedding_dim,
        #     ),
        # )

        # ------- 自定义 Embedding 函数（维度和 token 数）-------
        @wrap_embedding_func_with_attrs(
            embedding_dim=1024,          # 千问 text-embedding-v4 向量维度
            max_token_size=2048          # 千问 embedding 最大 token 数
        )
        async def qwen_embedding(texts: list[str]) -> np.ndarray:
            client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            resp = await client.embeddings.create(
                model=self.embedding_model,
                input=texts,
            )
            return np.array([d.embedding for d in resp.data])

        # 构建 LLM 和 Embedding 函数
        self.llm_model_func = openai_complete
        self.embedding_func = qwen_embedding


        self.rag = LightRAG(
            working_dir=str(self.working_dir),
            llm_model_func=self.llm_model_func,
            llm_model_name=self.llm_model,
            llm_model_kwargs=self.llm_kwargs,
            embedding_func=self.embedding_func,
        )

        self._initialized = False
    async def _ensure_initialized(self):
        if not self._initialized:
            await self.rag.initialize_storages()
            self._initialized = True

    # ------- 自定义 Embedding 函数（维度和 token 数）-------
    @wrap_embedding_func_with_attrs(
        embedding_dim=1024,          # 千问 text-embedding-v2 向量维度
        max_token_size=2048          # 千问 embedding 最大 token 数
    )
    async def qwen_embedding(texts: list[str]) -> np.ndarray:
        client = AsyncOpenAI(
            api_key=os.environ["DASHSCOPE_API_KEY"],
            base_url=rag_conf["base_url"],
        )
        resp = await client.embeddings.create(
            model=rag_conf["embedding_model_name"],
            input=texts,
        )
        return np.array([d.embedding for d in resp.data])

    # ------------------------------------------------------------------
    # 文本提取辅助方法
    # ------------------------------------------------------------------
    @staticmethod
    def _read_md_file(file_path: str) -> str:
        """读取 Markdown 文件内容。"""
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _read_pdf_file(file_path: str, page_list: Optional[list] = None) -> str:
        """使用  提取 PDF 文本。"""

        text_parts: List[str] = []
        with pdfplumber.open(file_path) as pdf:
            if page_list is None:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            else:
                for st, ed in page_list:
                    for i in range(st-1, ed):
                        page_text = pdf.pages[i].extract_text()
                        if page_text:
                            text_parts.append(page_text)

        combined = "\n".join(text_parts)

        # with open(file_path, "rb") as f:
        #     reader = PyPDF2.PdfReader(f)
        #     for page in reader.pages:
        #         page_text = page.extract_text()
        #         if page_text:
        #             text_parts.append(page_text)
        # combined = "\n".join(text_parts)

        if not combined.strip():
            raise ValueError(f"未能从 PDF 文件中提取到文本: {file_path}")
        return combined

    # ------------------------------------------------------------------
    # 同步插入方法
    # ------------------------------------------------------------------
    def insert_string(self, content: str) -> None:
        """插入纯文本字符串。"""
        self.rag.insert(content)

    def insert_md_file(self, file_path: str) -> None:
        """插入 Markdown 文件 (.md)。"""
        content = self._read_md_file(file_path)
        self.rag.insert(content)

    def insert_pdf_file(self, file_path: str, page_list: Optional[list] = None) -> None:
        """插入 PDF 文件 (.pdf)。"""
        text = self._read_pdf_file(file_path, page_list)
        self.rag.insert(text, file_paths=file_path)

    def insert(self, input_data: str, page_list: Optional[list] = None) -> None:
        """
        通用插入接口，自动判断输入类型：

        * 以 ``.md`` 结尾 → Markdown 文件
        * 以 ``.pdf`` 结尾 → PDF 文件
        * 其他 → 纯文本字符串
        """
        if input_data.endswith(".md"):
            self.insert_md_file(input_data)
        elif input_data.endswith(".pdf"):
            self.insert_pdf_file(input_data, page_list)
        else:
            self.insert_string(input_data)

    # ------------------------------------------------------------------
    # 异步插入方法
    # ------------------------------------------------------------------
    async def ainsert_string(self, content: str) -> None:
        """异步插入纯文本字符串。"""
        await self._ensure_initialized()
        await self.rag.ainsert(content)

    async def ainsert_md_file(self, file_path: str) -> None:
        """异步插入 Markdown 文件。"""
        await self._ensure_initialized()
        content = self._read_md_file(file_path)
        await self.rag.ainsert(content)

    async def ainsert_pdf_file(self, file_path: str) -> None:
        """异步插入 PDF 文件。"""
        await self._ensure_initialized()
        text = self._read_pdf_file(file_path)
        await self.rag.ainsert(text)

    async def ainsert(self, input_data: str) -> None:
        """
        通用异步插入接口，自动判断输入类型：

        * 以 ``.md`` 结尾 → Markdown 文件
        * 以 ``.pdf`` 结尾 → PDF 文件
        * 其他 → 纯文本字符串
        """
        await self._ensure_initialized()
        if input_data.endswith(".md"):
            await self.ainsert_md_file(input_data)
        elif input_data.endswith(".pdf"):
            await self.ainsert_pdf_file(input_data)
        else:
            await self.ainsert_string(input_data)

    # ------------------------------------------------------------------
    # 查询方法
    # ------------------------------------------------------------------
    _VALID_MODES = {"local", "global", "hybrid", "naive", "mix", "bypass"}

    def query(self, question: str, mode: str = "hybrid", top_k: int = 10, only_need_context: bool = False, **query_kwargs) -> str:
        """
        同步查询。

        Parameters
        ----------
        question : str
            查询问题。
        mode : str
            查询模式，可选值：``local``, ``global``, ``hybrid``, ``naive``, ``mix``, ``bypass``。
        **query_kwargs
            传入 ``QueryParam`` 的其他参数（如 ``stream``, ``top_k``, only_need_context 等）。

        Returns
        -------
        str
            LightRAG 生成的回答。
        """
        if mode not in self._VALID_MODES:
            raise ValueError(
                f"无效查询模式: {mode}。允许值: {sorted(self._VALID_MODES)}"
            )
        param = QueryParam(mode=mode, top_k=top_k, only_need_context=only_need_context, **query_kwargs)
        return self.rag.query(question, param=param)

    async def aquery(self, question: str, mode: str = "local", top_k: int = 10, only_need_context: bool = False, **query_kwargs) -> str:
        """
        异步查询。

        Parameters
        ----------
        question : str
            查询问题。
        mode : str
            查询模式，可选值：``local``, ``global``, ``hybrid``, ``naive``, ``mix``, ``bypass``。
        **query_kwargs
            传入 ``QueryParam`` 的其他参数。

        Returns
        -------
        str
            LightRAG 生成的回答。
        """
        await self._ensure_initialized()
        if mode not in self._VALID_MODES:
            raise ValueError(
                f"无效查询模式: {mode}。允许值: {sorted(self._VALID_MODES)}"
            )
        param = QueryParam(mode=mode, top_k=top_k, only_need_context=only_need_context, **query_kwargs)
        return await self.rag.aquery(question, param=param)


# ============================================================================
# 使用示例 (可直接运行)
# ============================================================================
# blue_formation, blue_weapon, blue_task
# red_formation, red_weapon, red_task
if __name__ == "__main__":

    # for name, lis in mapping.items():
    #     # ---- 初始化 ----
    #     wrapper = LightRAGWrapper(
    #         working_dir=f"./{name}",          # 数据存储目录
    #         api_key=os.environ.get("OPENAI_API_KEY"),          # 替换为真实 API Key
    #         base_url=rag_conf["base_url"], # 或自定义的 OpenAI‑兼容端点
    #         llm_model=rag_conf["chat_model_name"],
    #         embedding_model=rag_conf["embedding_model_name"],
    #         embedding_dim=1536,
    #     )
    #     for item in lis:
    #         # 方式 3：插入 PDF 文件
    #         wrapper.insert("D:\\Academic resources\\ARN34828-ADP_3-90-000-WEB-1.pdf", item[0], item[1])            # 确保文件存在
    #         time.sleep(2)

    # ---- 初始化 ----
    wrapper = LightRAGWrapper(
        working_dir="./environment",          # 数据存储目录
        api_key=os.environ.get("OPENAI_API_KEY"),          # 替换为真实 API Key
        base_url=rag_conf["base_url"], # 或自定义的 OpenAI‑兼容端点
        llm_model=rag_conf["chat_model_name"],
        embedding_model=rag_conf["embedding_model_name"],
    )
    # 方式 3：插入 PDF 文件
    # wrapper.insert("D:\\Academic resources\\WEAPON_SYSTEMS_HANDBOOK.pdf", [()])            # 确保文件存在
        

    # ---- 插入数据 ----
    # 方式 1：直接插入字符串
    # wrapper.insert("LightRAG 是一个简单快速的检索增强生成系统。")

    # 方式 2：插入 Markdown 文件
    # wrapper.insert("D:\\Academic resources\\KB\\军事地理气象知识.md")      # 确保文件存在


    # ---- 查询 ----
    asyncio.run(wrapper._ensure_initialized())
    answer = wrapper.query("什么天气适合进攻", mode="local", only_need_context=True)
    # print("答案:", answer)

    # ---- 异步示例 ----
    async def async_demo():
        await wrapper.ainsert("异步插入测试文本")
        resp = await wrapper.aquery("测试问题", mode="local", only_need_context=True)
        print("异步答案:", resp)

    # 取消注释以运行异步示例
    # asyncio.run(async_demo())