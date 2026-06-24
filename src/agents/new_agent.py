

import asyncio
import json
from agents.react_agent import background_agent, formation_agent, task_agent, output_agent, revise_agent, summary_agent
from langchain.messages import AIMessageChunk
from utils.logger import get_logger
from utils.chat_history_handler import get_conv_store
from utils.config_handler import db_conf
from rag.rag import RAG

logger = get_logger()

# def run_background_agent(user_input: str):
#     for c in "正在查询地理与气象知识库，请稍等...":
#         await asyncio.sleep(0.1)
#         yield c
#     background = await background_agent.ainvoke(user_input)
#     for c in "地理与气象知识库查询完成！":
#         await asyncio.sleep(0.1)
#         yield c

# def run_formation_agent(user_input: str):
#     for c in "正在查询红蓝双方兵力部署与武器知识库，请稍等...":
#             await asyncio.sleep(0.1)
#             yield c
#     formation = await formation_agent.ainvoke(user_input)
#     for c in "红蓝双方兵力部署与武器知识库查询完成！":
#         await asyncio.sleep(0.1)
#         yield c

# def run_task_agent(user_input: str):
#     for c in "正在查询红蓝双方战术与任务知识库，请稍等...":
#             await asyncio.sleep(0.1)
#             yield c
#     task = await task_agent.ainvoke(user_input)
#     for c in "红蓝双方战术与任务知识库查询完成！":
#         await asyncio.sleep(0.1)
#         yield c

async def invoke_agent(agent, input: list[str]):
    input_dict = {
        "messages": [{"role": "user", "content": msg} for msg in input]
    }
    result = await agent.ainvoke(input_dict)
    return result['messages'][-1].content.strip()

async def stream_agent(agent, input: list[str]):
    input_dict = {
        "messages": [{"role": "user", "content": msg} for msg in input]
    }
    async for chunk, metadata in agent.astream(input_dict, stream_mode="messages"):
        if isinstance(chunk, AIMessageChunk):
            yield chunk.content
            # print(chunk.content, end="")
async def run_agent(user_input: str, conv_id: str):
    conv_store = await get_conv_store()

    # 1. 获取 background
    background = await conv_store.get_config_field(conv_id, "background")

    if background is None:
        # 未命中缓存，需要调用 agent
        background_task = asyncio.create_task(
            invoke_agent(background_agent, [user_input])
        )

        await asyncio.sleep(1)
        for c in "正在查询地理与气象知识库，请稍等...\n\n":
            await asyncio.sleep(0.1)
            yield {"thinking": c}

        try:
            background = await background_task
        except Exception as e:
            logger.error(f"background_agent 执行失败: {e}")

        for c in "地理与气象知识库查询完成！\n\n":
            await asyncio.sleep(0.1)
            yield {"thinking": c}

        store_background = asyncio.create_task(conv_store.set_config_field(conv_id, "background", background))

    # 2. 获取 formation
    formation = await conv_store.get_config_field(conv_id, "formation")

    if formation is None:

        formation_task = asyncio.create_task(
            invoke_agent(formation_agent, [background])
        )

        await asyncio.sleep(1)
        for c in "正在查询红蓝双方兵力部署与武器知识库，请稍等...\n\n":
            await asyncio.sleep(0.1)
            yield {"thinking": c}

        try:
            formation = await formation_task
        except Exception as e:
            logger.error(f"formation_agent 执行失败: {e}")

        for c in "红蓝双方兵力部署与武器知识库查询完成！\n\n":
            await asyncio.sleep(0.1)
            yield {"thinking": c}

        store_formation = asyncio.create_task(conv_store.set_config_field(conv_id, "formation", formation))

    # 3. 获取 task
    task = await conv_store.get_config_field(conv_id, "task")
    if task is None:

        task_task = asyncio.create_task(
            invoke_agent(task_agent, [background, formation])
        )

        await asyncio.sleep(1)
        for c in "正在查询红蓝双方战术与任务知识库，请稍等...\n\n":
            await asyncio.sleep(0.1)
            yield {"thinking": c}

        try:
            task = await task_task
        except Exception as e:
            logger.error(f"formation_agent 执行失败: {e}")

        for c in "红蓝双方战术与任务知识库查询完成！\n\n":
            await asyncio.sleep(0.1)
            yield {"thinking": c}

        store_task = asyncio.create_task(conv_store.set_config_field(conv_id, "task", task))

    async for chunk in stream_agent(output_agent, [background, formation, task]):
        yield {"content": chunk}

    try:
        await store_background
        await store_formation
        await store_task
    except asyncio.CancelledError:
        pass


async def run_agent_summary(user_input: str, max_retries=2):

    rag = RAG(db_conf["feedback_collection_name"])

    for attempt in range(max_retries):
        try:
            json_str = await invoke_agent(summary_agent, [user_input])
            records = json.loads(json_str)
            for rec in records:
                content = json.dumps(rec, ensure_ascii=False)
                await rag.aadd_text(content, "feedback")
            return
        
        except json.JSONDecodeError as e:
            logger.error(e)
            await asyncio.sleep(0.1)
            continue

async def run_agent_again(user_input: str, conv_id: str):

    summary_task = asyncio.create_task(run_agent_summary(user_input))

    await asyncio.sleep(1)

    for c in "正在根据建议进行修改，请稍等...\n":
        yield {"thinking": c}
        await asyncio.sleep(0.1)


    async for chunk in stream_agent(revise_agent, [user_input]):
        yield {"content": chunk}

    try:
        await summary_task
    except asyncio.CancelledError:
        pass

    

async def main():
    user_input = ""
    # async for chunk in stream_agent(output_agent, ""):
    # async for chunk in stream_agent(output_agent, background+"\n\n"+formation+"\n\n"+task):
    # async for chunk in stream_agent(task_agent, "你现在的设定是什么？"):
        # yield {"content": chunk}
        # print(chunk, end="")
    await run_agent_summary(user_input)

if __name__ == "__main__":
    asyncio.run(main())
