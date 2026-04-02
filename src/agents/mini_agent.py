from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from rag.rag import RAG
from utils.logger import get_logger
from utils.config_handler import prompts_conf
from models.factory import chat_model
from utils.path_tools import get_abs_path
from utils.prompt_loader import load_summary_prompt

logger = get_logger()

class MiniAgent:
    # 类变量缓存，所有实例共用

    def __init__(self, vector_store: RAG, load_prompt):
        self.vector_store = vector_store
        self.prompt_text = load_prompt()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.model = chat_model
        self.chain = self._init_chain()

    def _init_chain(self):
        chain = self.prompt_template | self.model | StrOutputParser()
        return chain

    def get_docs(self, query: str) -> list[Document]:
        return self.vector_store.get_relevant_knowledge(query)

    def execute(self, input: str, load_examples=None) -> str:
        # key: input, for user query
        # key: context, 参考资料
        input_dict = {}

        context_docs = self.get_docs(input)
        context = ""
        counter = 0
        for doc in context_docs:
            counter += 1
            context += f"【参考资料{counter}】：参考资料：{doc.page_content} | 参考元数据：{doc.metadata}\n"
        input_dict["input"] = input
        input_dict["context"] = context
        if (load_examples != None):
            input_dict["examples"] = load_examples()

        return self.chain.invoke(input_dict)


# for testing
if __name__ == '__main__':
    

    pass
