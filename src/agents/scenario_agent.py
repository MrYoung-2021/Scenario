import json
from langgraph.graph import StateGraph, END, add_messages
from langgraph.runtime import Runtime
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from typing import Annotated, Dict, Any, Optional, TypedDict
from rag.rag import RAG
from agents.mini_agent import MiniAgent
from utils.prompt_loader import load_text_prompt
from utils.logger import get_logger
from agents.react_agent import ReactAgent
from models.factory import chat_model
from utils.config_handler import chroma_conf, agent_conf
from utils.skills_loader import load_json_examples, load_text_examples

logger = get_logger()

# 定义状态结构
class ScenarioState(TypedDict):
    user_input: str
    session_id: str
    scenario: Dict[str, Any]
    scenario_str: str
    scenario_text: str
    evaluation_result: Dict[str, Any]
    feedback: str
    review_status: str
    review_comment: str
    messages: Annotated[list, add_messages]


# 输入预处理模块
def input_preprocessing(state: ScenarioState) -> ScenarioState:
    """预处理用户输入，提取关键信息"""
    # 简单的输入预处理逻辑，实际应用中可能需要更复杂的NLP处理
    user_input = state["user_input"]
    logger.info(f"开始预处理用户输入: {user_input}")

    logger.info(f"输入预处理完成")
    return state

# Scenario Agent模块
def scenario_agent(state: ScenarioState) -> ScenarioState:
    """基于预处理的输入生成想定"""
    logger.info("开始生成想定")
    # 初始化LightRAG
    rag = RAG()
    
    # 这里应该调用LLM来生成想定，实际应用中需要集成具体的LLM
    # 现在使用一个简单的示例想定，并参考知识库中的知识

    react_agent = ReactAgent()

    scenario_str = react_agent.execute(state["user_input"], load_json_examples, state["session_id"])
    scenario = {}
    try:
        scenario = json.loads(scenario_str)
    except Exception as e:
        logger.error(f"解析json发生以下错误：{e}\n原字符串为：{scenario_str}")

    # scenario = {
    #     "name": "示例想定",
    #     "type": scenario_type,
    #     "background": "地区冲突升级",
    #     "timeframe": {
    #         "start": "2024-01-01",
    #         "end": "2024-01-07"
    #     },
    #     "red_force": {
    #         "organization": "机械化步兵师",
    #         "mission": "夺取战略要地",
    #         "area": "北部山区",
    #         "capabilities": {
    #             "strengths": ["装备先进", "训练有素"],
    #             "weaknesses": ["后勤补给困难"]
    #         }
    #     },
    #     "blue_force": {
    #         "organization": "装甲旅",
    #         "mission": "防御战略要地",
    #         "area": "北部山区",
    #         "capabilities": {
    #             "strengths": ["地形熟悉", "防御工事完善"],
    #             "weaknesses": ["装备老化"]
    #         }
    #     },
    #     "battlefield_environment": {
    #         "terrain": "山地地形，起伏较大",
    #         "weather": "冬季，低温，可能降雪",
    #         "electromagnetic": "存在轻度电磁干扰",
    #         "time_factors": "昼夜温差大，夜间能见度低"
    #     },
    #     "phases": [
    #         {
    #             "name": "侦察阶段",
    #             "actions": "双方进行侦察活动，收集情报"
    #         },
    #         {
    #             "name": "进攻阶段",
    #             "actions": "红方发起进攻，蓝方组织防御"
    #         },
    #         {
    #             "name": "收尾阶段",
    #             "actions": "双方调整部署，评估战果"
    #         }
    #     ],
    #     "assessment": {
    #         "casualties": {
    #             "red": "轻度",
    #             "blue": "中度"
    #         },
    #         "mission_completion": 75,
    #         "combat_effectiveness": 80
    #     },
    #     "special_cases": {
    #         "emergencies": ["可能出现恶劣天气"],
    #         "restrictions": ["禁止使用化学武器"]
    #     },
    #     "relevant_knowledge": relevant_knowledge  # 添加相关知识
    # }
    state["scenario"] = scenario
    state["scenario_str"] = scenario_str
    logger.info(f"想定生成完成！")
    return state

def convert_agent(state: ScenarioState) -> ScenarioState:

    logger.info(f"开始生成文本版想定")
    convert_agent = MiniAgent(RAG(), load_text_prompt)
    text = convert_agent.execute(state["scenario_str"], load_text_examples)
    state["scenario_text"] = text
    logger.info("已生成文本版想定")

    return state

# 想定评估模块
def machine_review(state: ScenarioState) -> ScenarioState:
    """评估想定的合理性和完整性"""
    logger.info("开始评估想定")
    # 简单的评估逻辑，实际应用中应该基于规则和LLM进行更复杂的评估
    scenario = state["scenario"]
    evaluation_result = {
        "passed": True,
        "issues": [],
        "suggestions": []
    }


    
    # 检查必要字段
    required_fields = ["name", "type", "background", "timeframe", "red_force", "blue_force", "battlefield_environment", "phases", "assessment"]
    for field in required_fields:
        if field not in scenario:
            evaluation_result["passed"] = False
            evaluation_result["issues"].append(f"缺少必要字段: {field}")
            evaluation_result["suggestions"].append(f"添加{field}字段")
    
    # 检查时间线
    if "timeframe" in scenario:
        if scenario["timeframe"].get("end") <= scenario["timeframe"].get("start"):
            evaluation_result["passed"] = False
            evaluation_result["issues"].append("结束时间早于或等于开始时间")
            evaluation_result["suggestions"].append("调整结束时间，使其晚于开始时间")
    
    # 检查作战阶段
    if "phases" in scenario and len(scenario["phases"]) == 0:
        evaluation_result["passed"] = False
        evaluation_result["issues"].append("作战阶段为空")
        evaluation_result["suggestions"].append("添加至少一个作战阶段")
    


    state["evaluation_result"] = evaluation_result
    status = "通过" if evaluation_result["passed"] else "不通过"
    logger.info(f"想定评估完成，结果: {status}")
    if not evaluation_result["passed"]:
        logger.warning(f"评估发现问题: {'; '.join(evaluation_result['issues'])}")
    return state

def human_review(state: ScenarioState) -> ScenarioState:
    # 人工检验环节
    logger.info("进入人工校验环节")
    human_feedback = interrupt(f"初步想定为以下内容：{state["scenario_text"]}\n输入 'approve' 批准，或输入 'reject' 并附上修改意见")

    # 解析人工输入
    if isinstance(human_feedback, str) and human_feedback.lower().startswith("approve"):
        # 批准
        return Command(
            goto="output_scenario",
            update={
                "review_status": "approved",
                "review_comment": "已批准"
            }
        )
    elif isinstance(human_feedback, str) and human_feedback.lower().startswith("reject"):
        # 拒绝，提取修改意见
        comment = human_feedback.replace("reject", "", 1).replace(":", "", 1).strip()
        if not comment:
            comment = "未提供具体意见"
        return Command(
            goto="record_issues",
            update={
                "review_status": "record_issues",
                "review_comment": comment
            }
        )
    else:
        # 默认处理：视为拒绝
        return Command(
            goto="record_issues",
            update={
                "review_status": "rejected",
                "review_comment": f"无效输入: {human_feedback}"
            }
        )

# 问题记录+经验库模块
def record_issues(state: ScenarioState) -> ScenarioState:
    """记录问题并添加到经验库"""
    logger.info("开始记录问题")
    # 简单的问题记录逻辑，实际应用中应该将问题存储到数据库或文件中
    issues = state["evaluation_result"].get("issues", [])
    suggestions = state["evaluation_result"].get("suggestions", [])
    feedback = f"发现以下问题及相应的建议: {'; '.join(f"{a},{b}" for a, b in zip(issues, suggestions))}"
    state["feedback"] = feedback
    # 将问题添加到经验库
    rag = RAG(chroma_conf["feedback_collection_name"])
    rag.add_text(feedback, state["session_id"])

    logger.info("问题记录完成")
    return state

# 反思迭代机制
def reflection_iteration(state: ScenarioState) -> ScenarioState:
    """基于评估结果进行反思和迭代"""
    
    return state

# 输出仿真想定模块
def output_scenario(state: ScenarioState) -> ScenarioState:
    """输出最终的仿真想定"""
    logger.info("开始输出最终想定")
    state["final_scenario"] = state["scenario"]
    logger.info(f"最终想定输出完成，想定名称: {state["scenario"].get('name', '未知')}")
    return state

# 构建LangGraph
scenario_graph = StateGraph(ScenarioState)

# 添加节点
scenario_graph.add_node("input_preprocessing", input_preprocessing)
scenario_graph.add_node("scenario_agent", scenario_agent)
scenario_graph.add_node("convert_agent", convert_agent)
scenario_graph.add_node("machine_review", machine_review)
scenario_graph.add_node("human_review", human_review)
scenario_graph.add_node("record_issues", record_issues)
scenario_graph.add_node("reflection_iteration", reflection_iteration)
scenario_graph.add_node("output_scenario", output_scenario)

# 添加边
scenario_graph.set_entry_point("input_preprocessing")
scenario_graph.add_edge("input_preprocessing", "scenario_agent")
scenario_graph.add_edge("scenario_agent", "convert_agent")
scenario_graph.add_edge("convert_agent", "machine_review")
scenario_graph.add_edge("machine_review", "human_review")

# 条件边：根据评估结果决定下一步
# scenario_graph.add_conditional_edges(
#     "human_review",
#     lambda state: "record_issues" if not state["evaluation_result"].get("passed", False) else "output_scenario"
# )

scenario_graph.add_edge("human_review", "output_scenario")


scenario_graph.add_edge("record_issues", "reflection_iteration")
scenario_graph.add_edge("reflection_iteration", "scenario_agent")  # 重新生成想定
scenario_graph.add_edge("output_scenario", END)

# 编译图
graph = scenario_graph.compile(checkpointer=MemorySaver())

# 运行agent的函数
def run_scenario_agent(user_input: str) -> Dict[str, Any]:
    """运行Scenario Agent生成仿真想定"""
    logger.info(f"开始运行Scenario Agent，用户输入: {user_input}")
    # initial_state = ScenarioState()
    initial_state: ScenarioState = {
        "feedback": "",
        "evaluation_result": "",
        "session_id": agent_conf["thread_id"]
    }
    initial_state["user_input"] = user_input

    config = {"configurable": {"thread_id": agent_conf["thread_id"]}}
    
    # 运行图
    # result = {"scenario_text": ""}
    for chunk, metadata in graph.stream(initial_state, config=config, stream_mode="messages"):
        if chunk.content:
            print(chunk, end="|\n", flush=True)

    # result = graph.invoke(initial_state, config)
    print("="*30)

    sys_info = list(graph.get_state(config))

    # print(f"{result.get('__interrupt__')[0].value}\n请输入：", end="")
    # print(f"{sys_info[-1][0].value}\n请输入：", end="")
    print(f"请输入：", end="")

    user_advice = input()
    
    for chunk, metadata in graph.stream(Command(resume=user_advice), config=config, stream_mode="messages"):
        if chunk.content:
            print(chunk, end="|\n", flush=True)

    print("="*50)

    # result = graph.invoke(Command(resume=user_advice), config)

    
    # 返回最终结果
    logger.info("Scenario Agent运行完成")
    # return {
    #     "final_scenario": result["scenario_text"],
    #     "evaluation_result": result["evaluation_result"],
    #     "feedback": result["feedback"],
    # }

if __name__ == "__main__":
    run_scenario_agent("生成一个占领高山阵地的响应")