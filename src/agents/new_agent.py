

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from agents.react_agent import background_agent, formation_agent, task_agent, output_agent, revise_agent, summary_agent
from langchain.messages import AIMessageChunk
from utils.logger import get_logger
from utils.chat_history_handler import get_conv_store
from utils.config_handler import db_conf, rag_conf
from rag.rag import RAG
from schemas.scenario import GenerationMode, StepType

logger = get_logger()


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


def _structured_prompt(
    selections: dict[str, Any],
    confirmed_context: dict[str, Any],
    retrieved_knowledge: list[dict[str, Any]] | None = None,
    extra: str | None = None,
) -> str:
    selections = dict(selections)
    custom_requirements = selections.pop("custom_requirements", "")
    blocks = (
        ("USER_SELECTIONS", selections),
        ("CUSTOM_REQUIREMENTS", custom_requirements),
        ("CONFIRMED_CONTEXT", confirmed_context),
        (
            "RETRIEVED_KNOWLEDGE",
            retrieved_knowledge
            if retrieved_knowledge is not None
            else "Use the bound knowledge tools and preserve their source scope.",
        ),
    )
    prompt = "\n\n".join(
        f"<{name}>\n{json.dumps(value, ensure_ascii=False, indent=2)}\n</{name}>"
        for name, value in blocks
    )
    if extra:
        prompt = f"{prompt}\n\n<STEP_INSTRUCTION>\n{extra}\n</STEP_INSTRUCTION>"
    return prompt


async def generate_background(input_model: dict[str, Any]) -> AsyncIterator[str]:
    prompt = _structured_prompt(input_model, {})
    async for chunk in stream_agent(background_agent, [prompt]):
        yield chunk


async def generate_formation(
    input_model: dict[str, Any],
    confirmed_background: dict[str, Any],
) -> AsyncIterator[str]:
    prompt = _structured_prompt(
        input_model,
        {"background": confirmed_background},
    )
    async for chunk in stream_agent(formation_agent, [prompt]):
        yield chunk


async def generate_task(
    input_model: dict[str, Any],
    confirmed_background: dict[str, Any],
    confirmed_formation: dict[str, Any],
) -> AsyncIterator[str]:
    prompt = _structured_prompt(
        input_model,
        {
            "background": confirmed_background,
            "formation": confirmed_formation,
        },
    )
    async for chunk in stream_agent(task_agent, [prompt]):
        yield chunk


async def generate_final(
    confirmed_background: dict[str, Any],
    confirmed_formation: dict[str, Any],
    confirmed_task: dict[str, Any],
) -> AsyncIterator[str]:
    prompt = _structured_prompt(
        {},
        {
            "background": confirmed_background,
            "formation": confirmed_formation,
            "task": confirmed_task,
        },
        extra=(
            "Integrate only the confirmed context into the final document. "
            "Do not change confirmed facts or silently fill conflicts."
        ),
    )
    async for chunk in stream_agent(output_agent, [prompt]):
        yield chunk


async def revise_step(
    step: StepType,
    current_output: str,
    instruction: str,
    confirmed_context: dict[str, Any],
) -> AsyncIterator[str]:
    prompt = _structured_prompt(
        {},
        confirmed_context,
        extra=(
            f"Revise only the '{step}' step.\n"
            f"REVISION_INSTRUCTION:\n{instruction}\n\n"
            f"CURRENT_STEP_OUTPUT:\n{current_output}\n\n"
            "Return the complete revised content for this step only. "
            "Never rewrite confirmed prerequisite content."
        ),
    )
    async for chunk in stream_agent(revise_agent, [prompt]):
        yield chunk


class LangChainScenarioGenerator:
    model_name = rag_conf["chat_model_name"]

    async def stream(
        self,
        step: StepType,
        mode: GenerationMode,
        input_data: dict[str, Any],
        confirmed_context: dict[str, Any],
        current_output: str | None = None,
        revision_instruction: str | None = None,
    ) -> AsyncIterator[str]:
        if mode == GenerationMode.REVISE:
            assert current_output is not None and revision_instruction is not None
            async for chunk in revise_step(
                step,
                current_output,
                revision_instruction,
                confirmed_context,
            ):
                yield chunk
            return
        if step == StepType.BACKGROUND:
            stream = generate_background(input_data)
        elif step == StepType.FORMATION:
            stream = generate_formation(input_data, confirmed_context["background"])
        elif step == StepType.TASK:
            stream = generate_task(
                input_data,
                confirmed_context["background"],
                confirmed_context["formation"],
            )
        else:
            stream = generate_final(
                confirmed_context["background"],
                confirmed_context["formation"],
                confirmed_context["task"],
            )
        async for chunk in stream:
            yield chunk
            
async def run_agent(user_input: str, conv_id: str):
    conv_store = await get_conv_store()
    store_tasks: list[asyncio.Task] = []

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
            raise

        for c in "地理与气象知识库查询完成！\n\n":
            await asyncio.sleep(0.1)
            yield {"thinking": c}

        store_tasks.append(
            asyncio.create_task(conv_store.set_config_field(conv_id, "background", background))
        )

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
            raise

        for c in "红蓝双方兵力部署与武器知识库查询完成！\n\n":
            await asyncio.sleep(0.1)
            yield {"thinking": c}

        store_tasks.append(
            asyncio.create_task(conv_store.set_config_field(conv_id, "formation", formation))
        )

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
            raise

        for c in "红蓝双方战术与任务知识库查询完成！\n\n":
            await asyncio.sleep(0.1)
            yield {"thinking": c}

        store_tasks.append(
            asyncio.create_task(conv_store.set_config_field(conv_id, "task", task))
        )

    async for chunk in stream_agent(output_agent, [background, formation, task]):
        yield {"content": chunk}

    if store_tasks:
        await asyncio.gather(*store_tasks)


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
