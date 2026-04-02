from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.prompts import PromptTemplate
from agents.tools.middleware import trim_messages
from agents.tools.agent_tools import rag_summarize
from models.factory import chat_model
from utils.prompt_loader import load_scenario_prompt, load_system_prompt
from utils.path_tools import get_abs_path
from utils.config_handler import chroma_conf

# memory = SqliteSaver.from_conn_string(get_abs_path(chroma_conf["checkpointer_sql"]))
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
            tools=[rag_summarize],
            middleware=[summary_middleware],
            checkpointer=memory
        )

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

if __name__ == '__main__':
    agent = ReactAgent()
    print(agent.execute("生成一个陆战想定"))
        