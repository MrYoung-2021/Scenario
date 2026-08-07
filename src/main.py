#!/usr/bin/env python3
"""Scenario Agent 主入口文件"""

from contextlib import asynccontextmanager
from pathlib import Path
import sys
import json
import time

from rich.console import Console
from rich.panel import Panel
from rich.json import JSON

from rag.rag import RAG
from utils.logger import get_logger, get_log_file
from utils.config_handler import db_conf
from utils.config_handler import ConfigHandler
from agents.new_agent import run_agent, run_agent_again
from utils.chat_history_handler import get_conv_store
# from agents.test_agent import run_scenario_agent

console = Console()
logger = get_logger()
rag: RAG | None = None


def get_rag() -> RAG:
    """Initialize the standard knowledge base only when an endpoint needs it."""
    global rag
    if rag is None:
        rag = RAG()
    return rag


from fastapi import FastAPI, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio
import json
import uvicorn
from typing import Annotated, AsyncGenerator
from api.system_routes import router as system_router
from api.scenario_routes import router as scenario_router
from services.scenario_service import ScenarioServiceError





@asynccontextmanager
async def lifespan(app: FastAPI):
    # ========== 启动：初始化三个数据库 ==========
    
    # 1. SQLite3（同步连接，设置 check_same_thread=False 以便在多线程中使用）
    app.state.sqlite_conn = await get_conv_store()
    # 建议开启 WAL 模式提高并发性能
    # app.state.sqlite_conn.execute("PRAGMA journal_mode=WAL")
    
    yield  # 应用运行期间
    
    # ========== 关闭：释放所有资源 ==========
    
    # SQLite3 连接关闭
    if hasattr(app.state, 'sqlite_conn'):
        await app.state.sqlite_conn.close()

app = FastAPI(lifespan=lifespan)
app.include_router(system_router)
app.include_router(scenario_router)


@app.exception_handler(ScenarioServiceError)
async def scenario_service_error_handler(request: Request, exc: ScenarioServiceError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


static_dir = Path(__file__).parent / 'static'
app.mount(
    "/static",
    StaticFiles(directory=static_dir, html=True)
)

class ChatRequest(BaseModel):
    message: str
    conv_id: str
    title: str
    elements: str

class KnowledgeModel(BaseModel):
    kb_id: str
    content: str

class ElementModel(BaseModel):
    name: str
    element: str


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    接收用户消息并返回流式助手回复
    """
    conv_store = app.state.sqlite_conn
    cnt = await conv_store.get_turn_count(request.conv_id)
    async def generate_response():
        full_content = ""
        # 调用agent
        _run = run_agent_again
        input = f"用户修改意见：{request.message}\n原军事想定内容：{await conv_store.get_latest_assistant_message(request.conv_id)}"

        if cnt == 0:
            _run = run_agent
            input = f"用户输入：{request.message}\n要求使用武器：{request.elements}"

        async for chunk in _run(input, request.conv_id):
            # 将每个chunk转换为JSON并添加换行符以分隔
            if "content" in chunk:
                full_content += chunk["content"]
            yield json.dumps(chunk, ensure_ascii=False) + "\n"
        await conv_store.add_message(request.conv_id, "assistant", full_content)

    await conv_store.create_conversation_with_id(request.conv_id, request.title)
    await conv_store.add_message(request.conv_id, "user", request.message)
    # 返回流式响应
    return StreamingResponse(
        generate_response(),
        media_type="application/x-ndjson"  # 使用ndjson格式以支持逐行JSON
    )


@app.post("/api/test")
async def test_endpoint(request: ChatRequest):
    """
    接收用户消息并返回流式助手回复
    """
    conv_store = app.state.sqlite_conn
    async def generate_response():
        # 调用agent
        for chunk in f"{request.message}\n{request.conv_id}\n{request.elements}":
            # 将每个chunk转换为JSON并添加换行符以分隔
            await asyncio.sleep(0.1)
            yield json.dumps({"thinking": chunk}, ensure_ascii=False) + "\n"

        for chunk in f"{request.message}\n{request.conv_id}\n{request.elements}":
            # 将每个chunk转换为JSON并添加换行符以分隔
            await asyncio.sleep(0.1)
            yield json.dumps({"content": chunk}, ensure_ascii=False) + "\n"    
    
    await conv_store.create_conversation_with_id(request.conv_id, request.title)
    await conv_store.add_message(request.conv_id, "user", request.message)
    await conv_store.add_message(request.conv_id, "assistant", f"{request.message}\n{request.conv_id}\n{request.elements}")
    # print(f"这是第{conv_store.get_turn_count(request.conv_id)}轮对话")
    # 返回流式响应
    return StreamingResponse(
        generate_response(),
        media_type="application/x-ndjson"  # 使用ndjson格式以支持逐行JSON
    )


@app.get("/api/get_conversations")
async def get_conversations():
    """
    返回对话的id和title列表
    """
    conv_store = app.state.sqlite_conn
    return await conv_store.get_conversation_id_title_list()

@app.get("/api/get_messages")
async def get_messages(conv_id: str):
    conv_store = app.state.sqlite_conn
    return await conv_store.get_messages_formatted(conv_id)

@app.delete("/api/delete_conversation")
async def delete_conversation(conv_id: str):
    conv_store = app.state.sqlite_conn
    await conv_store.delete_conversation(conv_id)
    return {"success": True}


@app.get("/api/get_knowledge_bases")
async def get_knowledge_bases():
    """
    返回所有知识库列表
    """
    kb_list = [{"kb_id": "environment", "name": "环境知识库"}, {"kb_id": "formation", "name": "编成知识库"}, {"kb_id": "weapon", "name": "武器知识库"}, {"kb_id": "tactics", "name": "战术知识库"}, {"kb_id": "task", "name": "任务流程知识库"}, {"kb_id": "other", "name": "其他知识库"}]

    return kb_list

@app.get("/api/get_knowledge")
async def get_knowledge(
    kb_id: Annotated[list[str] | None, Query()] = None
):
    """
    根据kbId参数获取知识库的知识内容
    """
    knowledge_list = []
    for id in kb_id:
        knowledge_list += get_rag().get_texts_by_category(id)

    return knowledge_list

@app.post("/api/add_knowledge")
async def add_knowledge(request: KnowledgeModel):
    """
    添加知识库内容
    """
    # ids = await rag.aadd_text(request.content, request.kb_id)
    ids = get_rag().add_text(request.content, request.kb_id)
    return {"k_id": ids[0]}

@app.delete("/api/delete_knowledge")
async def delete_knowledge(k_id: str):
    """
    删除知识库的一条内容
    """
    res = await get_rag().adelete_text_by_id(k_id)
    return {"success": res}

@app.get("/api/get_elements")
async def get_elements():
    """
    获取装载元素json
    """
    return ConfigHandler.load_elements_json()

@app.post("/api/add_element")
async def add_element(request: ElementModel):
    """
    添加装载元素
    """
    ConfigHandler.update_elements_json({"name": request.name, "element": request.element})
    return {"success": True}

@app.delete("/api/delete_element")
async def delete_element(name: str, element: str):
    """
    添加装载元素
    """
    ConfigHandler.delete_element(name, element)
    return {"success": True}

@app.delete("/api/delete_category")
async def delete_category(name: str):
    """
    添加装载元素
    """
    ConfigHandler.delete_category(name)
    return {"success": True}


if __name__ == "__main__":
    # 运行服务
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
