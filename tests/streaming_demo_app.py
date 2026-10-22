"""브라우저 E2E 테스트에서만 쓰는 합성 스트리밍 Agent."""

import asyncio

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

import backend.main as backend_main


class DemoAgent:
    def __init__(self) -> None:
        self.history: dict[str, list[str]] = {}

    async def astream(self, values, config, stream_mode):
        thread_id = config["configurable"]["thread_id"]
        question = values["messages"][0]["content"]
        previous = list(self.history.get(thread_id, []))
        self.history.setdefault(thread_id, []).append(question)

        if question == "오류 확인":
            raise RuntimeError("synthetic stream failure")

        call_id = f"synthetic-{len(previous)}"
        yield "updates", {
            "model": {"messages": [AIMessage(content="", tool_calls=[{
                "id": call_id,
                "name": "search_operations_manual",
                "args": {"query": "synthetic"},
            }])]}
        }
        await asyncio.sleep(0.45)
        yield "updates", {
            "tools": {"messages": [ToolMessage(
                content="synthetic result",
                tool_call_id=call_id,
                name="search_operations_manual",
            )]}
        }
        answer = f"합성 응답. 이전 질문: {previous[-1] if previous else '없음'}. "
        for delay, part in ((0.25, answer), (0.8, f"현재 질문: {question}.")):
            await asyncio.sleep(delay)
            yield "messages", (AIMessageChunk(content=part), {})


async def demo_builder() -> DemoAgent:
    return DemoAgent()


backend_main.build_agent = demo_builder
app = backend_main.app
