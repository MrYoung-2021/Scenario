from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.prompts import PromptTemplate
from langchain.messages import AIMessageChunk
from agents.tools.middleware import trim_messages
from agents.tools.agent_tools import *
from models.factory import chat_model, qwen3_openai, mini_model
from utils.prompt_loader import load_scenario_prompt, load_system_prompt
from utils.path_tools import get_abs_path
from utils.prompt_loader import load_background_prompt, load_formation_prompt, load_task_prompt, load_revise_prompt

memory = MemorySaver()
summary_middleware = SummarizationMiddleware(
    model=chat_model,
    trigger=("tokens", 3000)
)

class ReactAgent(object):
    def __init__(self):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompt(),
            tools=[],
            middleware=[summary_middleware],
            checkpointer=memory
        )

    async def aexecute_stream(self, query, load_examples, id):
        user_prompt = PromptTemplate.from_template(load_scenario_prompt())

        input_dict = {
            "messages": [
                {"role": "user", "content": user_prompt.format(input=query, conditions="", examples=load_examples())},
            ]
        }

        session_config = {
            "configurable": {
                "thread_id": id
            }
        }

        async for chunk,metadata in self.agent.astream(input_dict, stream_mode="messages", config=session_config):
            if chunk.content:
                yield chunk.content

    def execute_stream(self, query, load_examples, id):
        user_prompt = PromptTemplate.from_template(load_scenario_prompt())

        input_dict = {
            "messages": [
                {"role": "user", "content": user_prompt.format(input=query, conditions="", examples=load_examples())},
            ]
        }

        session_config = {
            "configurable": {
                "thread_id": id
            }
        }

        for chunk in self.agent.stream(input_dict, stream_mode="values", config=session_config):
            latest_message = chunk["messages"][-1]  # 有历史记录所以取最后一条
            if latest_message.content:
                yield latest_message.content.strip() + "\n"

    def execute(self, query, load_examples, id):
        user_prompt = PromptTemplate.from_template(load_scenario_prompt())
        input_dict = {
            "messages": [
                {"role": "user", "content": user_prompt.format(input=query, conditions="", examples=load_examples())},
            ]
        }
        session_config = {
            "configurable": {
                "thread_id": id
            }
        }
        res = self.agent.invoke(input_dict, session_config)
        return res["messages"][-1].content.strip() + "\n"

# 实例agent
background_agent = create_agent(model=qwen3_openai, tools=[search_environment_KB], system_prompt=load_background_prompt(), name="background_agent")
formation_agent = create_agent(model=qwen3_openai, tools=[search_red_formation_KB, search_blue_formation_KB, search_red_weapon_KB, search_blue_weapon_KB], system_prompt=load_formation_prompt(), name="formation_agent")
task_agent = create_agent(model=qwen3_openai, tools=[search_red_weapon_KB, search_blue_weapon_KB, search_red_task_KB, search_blue_task_KB], system_prompt=load_task_prompt(), name="task_agent")
output_agent = create_agent(model=qwen3_openai, tools=[search_expert_KB, search_experience_KB], system_prompt=load_system_prompt(), name="output_agent")
revise_agent = create_agent(model=qwen3_openai, tools=[search_expert_KB, search_experience_KB, search_red_weapon_KB, search_blue_weapon_KB, search_task_KB], system_prompt=load_revise_prompt(), name="revise_agent")
summary_agent = create_agent(model=mini_model, tools=[], system_prompt=load_summary_prompt(), name="summary_agent")

if __name__ == '__main__':
    # input_dict = {
    #     "messages": [
    #         {"role": "user", "content": "你好"},
    #     ]
    # }
    # for chunk, metadata in revise_agent.stream(input_dict, stream_mode="messages"):
    #     if isinstance(chunk, AIMessageChunk):
    #         print(chunk.content, end="")
    print(load_summary_prompt())