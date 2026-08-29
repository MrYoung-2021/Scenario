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

from utils.logger import get_logger, get_log_file
from utils.config_handler import db_conf
from utils.config_handler import ConfigHandler
from agents.new_agent import run_agent, run_agent_again
from utils.chat_history_handler import get_conv_store
# from agents.test_agent import run_scenario_agent

console = Console()
logger = get_logger()
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import asyncio
import json
import uvicorn
from typing import AsyncGenerator
from api.system_routes import router as system_router
from api.location_routes import router as location_router
from api.scenario_routes import options_router as scenario_options_router
from api.scenario_routes import router as scenario_router
from api.knowledge_routes import router as knowledge_router
from services.scenario_service import ScenarioServiceError
from services.retrieval_registry import start_deposition_worker, stop_deposition_worker





@asynccontextmanager
async def lifespan(app: FastAPI):
    # ========== 启动：初始化三个数据库 ==========
    
    # 1. SQLite3（同步连接，设置 check_same_thread=False 以便在多线程中使用）
    app.state.sqlite_conn = await get_conv_store()
    await start_deposition_worker()
    # 建议开启 WAL 模式提高并发性能
    # app.state.sqlite_conn.execute("PRAGMA journal_mode=WAL")
    
    yield  # 应用运行期间
    
    # ========== 关闭：释放所有资源 ==========
    
    await stop_deposition_worker()
    # SQLite3 连接关闭
    if hasattr(app.state, 'sqlite_conn'):
        await app.state.sqlite_conn.close()
    if hasattr(app.state, 'location_service'):
        await app.state.location_service.close()

app = FastAPI(lifespan=lifespan)
app.include_router(system_router)
app.include_router(location_router)
app.include_router(scenario_router)
app.include_router(scenario_options_router)
app.include_router(knowledge_router)


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

class ElementModel(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    element: str = Field(min_length=1, max_length=100)


@app.post("/api/chat", deprecated=True)
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
        media_type="application/x-ndjson",  # 使用ndjson格式以支持逐行JSON
        headers={
            "Deprecation": "true",
            "Link": '</api/scenarios>; rel="successor-version"',
        },
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
    added = ConfigHandler.update_elements_json({"name": request.name, "element": request.element})
    return {"success": True, "added": added}

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
