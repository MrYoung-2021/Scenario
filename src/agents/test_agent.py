import uuid
from langgraph.graph import StateGraph, START, END
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from typing import TypedDict
from models.factory import chat_model
from langchain_community.chat_models.tongyi import ChatTongyi, BaseChatModel
from langchain_core.tools import tool
from langchain.messages import AIMessageChunk, ToolCallChunk, ToolMessage


cm = ChatTongyi(model="qwen3-max-2026-01-23", streaming=True)

@tool(description="从向量存储中检索参考资料")
def get_weather(query: str) -> str:
    return "今天天气晴转多云，晴时伴随有太阳雨"

model = create_agent(model=cm, tools=[get_weather])

class State(TypedDict):
    user_input: int
    result: str

def before_model(state: State):
    print("调用之前")

async def process(state: State):
    result = ""
    input_dict = {
            "messages": [
                {"role": "user", "content": state["user_input"]},
            ]
    }
    async for chunk in model.astream(input_dict, stream_mode="messages"):
        # print(chunk)
        # pass
        result = result + chunk.content
    # result = await model.ainvoke(input_dict)
    # result = model.invoke(input_dict)
    # async for chunk in chat_model.astream(state["user_input"]):
    #     pass
        
    return {"result": result}

def after_model(state: State):
    print("调用之后")

builder = StateGraph(State)
builder.add_node("before", before_model)
builder.add_node("process", process)
builder.add_node("after", after_model)
builder.add_edge(START, "before")
builder.add_edge("before", "process")
builder.add_edge("process", "after")
builder.add_edge("after", END)
graph = builder.compile()

# 运行agent的函数
async def run_scenario_agent(user_input: str):
    """运行Scenario Agent生成仿真想定"""
    # initial_state = ScenarioState()
    initial_state: State = {

    }
    initial_state["user_input"] = user_input

    
    # 运行图
    # result = {"scenario_text": ""}
    async for node, chunk in graph.astream(initial_state, stream_mode="messages", subgraphs=True):
        # if isinstance(chunk[0], AIMessageChunk)
        # print(chunk)
        # if isinstance(chunk[0], AIMessageChunk):
        #     print("111")
        # if isinstance(chunk[0], AIMessageChunk):
        #     print("111")
        # if isinstance(chunk[0], AIMessageChunk):
        #     print("111")
        if chunk[0].content:
            # print(chunk.content)
            yield {"content": chunk[0].content}
        # yield {"content": 111}
    # async for chunk in chat_model.astream(user_input):
    #     if chunk.content:
    #         yield {"content": chunk.content}

