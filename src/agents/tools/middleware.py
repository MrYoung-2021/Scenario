from langchain.agents.middleware import before_model
from langchain.agents import AgentState
from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

@before_model
def trim_messages(state: AgentState, runtime) -> dict | None:
    """在模型调用前裁剪消息历史"""
    messages = state["messages"]
    
    if len(messages) <= 10:
        return None   # 消息未超标，无需处理
    
    # 保留第一条 + 最近九条
    new_messages = [messages[0]] + messages[-9:]
    
    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),  # 清空旧消息
            *new_messages                            # 设置新消息
        ]
    }
