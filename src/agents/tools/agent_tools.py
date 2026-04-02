from langchain_core.tools import tool
from langgraph.prebuilt.tool_node import ToolCallRequest


from utils.path_tools import get_abs_path
from utils.prompt_loader import load_summary_prompt
from rag.rag import RAG
from agents.mini_agent import MiniAgent

rag_service = MiniAgent(RAG(), load_summary_prompt)
@tool(description="从向量存储中检索参考资料")
def rag_summarize(query: str) -> str:
    return rag_service.execute(query)