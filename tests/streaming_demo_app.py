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


class DemoSupervisor:
    def __init__(self) -> None:
        self.history: dict[str, list[str]] = {}

    async def astream(self, values, config, stream_mode, subgraphs):
        assert subgraphs is True
        thread_id = config["configurable"]["thread_id"]
        question = values["messages"][0]["content"]
        previous = list(self.history.get(thread_id, []))
        self.history.setdefault(thread_id, []).append(question)
        tasks = [
            {"id": "task_1", "description": "합성 매뉴얼 조회", "agent": "research", "status": "pending", "result": None},
            {"id": "task_2", "description": "답변 작성", "agent": "writing", "status": "pending", "result": None},
        ]
        yield (), "updates", {"planning": {"plan": "매뉴얼을 확인하고 답변합니다.", "tasks": tasks}}
        tasks = [{**tasks[0], "status": "in_progress"}, tasks[1]]
        yield (), "updates", {"start_task": {"tasks": tasks}}
        if question == "오류 확인":
            raise RuntimeError("synthetic supervisor failure")

        call_id = "supervisor-call"
        await asyncio.sleep(0.35)
        yield ("execute_task:research",), "updates", {"model": {"messages": [AIMessage(
            content="", tool_calls=[{"id": call_id, "name": "search_operations_manual", "args": {"query": "synthetic"}}],
        )]}}
        await asyncio.sleep(0.8)
        yield ("execute_task:research",), "updates", {"tools": {"messages": [ToolMessage(
            content="합성 매뉴얼 결과", tool_call_id=call_id, name="search_operations_manual",
        )]}}
        yield ("execute_task:research",), "messages", (
            AIMessageChunk(content="매뉴얼 확인 중"), {"langgraph_node": "model"},
        )
        tasks = [{**tasks[0], "status": "completed", "result": "합성 매뉴얼 결과"}, tasks[1]]
        yield (), "updates", {"execute_task": {"tasks": tasks, "current_task_index": 1}}
        tasks = [tasks[0], {**tasks[1], "status": "in_progress"}]
        yield (), "updates", {"start_task": {"tasks": tasks}}
        await asyncio.sleep(0.8)
        yield ("execute_task:writing",), "messages", (
            AIMessageChunk(content="답변 작성 중"), {"langgraph_node": "model"},
        )
        await asyncio.sleep(0.8)
        answer = f"합성 Supervisor 답변. 이전 질문: {previous[-1] if previous else '없음'}. 현재 질문: {question}."
        tasks = [tasks[0], {**tasks[1], "status": "completed", "result": answer}]
        yield (), "updates", {"execute_task": {"tasks": tasks, "current_task_index": 2}}
        yield (), "updates", {"finalize": {"messages": [AIMessage(content=answer)]}}


async def demo_supervisor_builder() -> DemoSupervisor:
    return DemoSupervisor()


backend_main.build_agent = demo_builder
backend_main.build_supervisor_graph = demo_supervisor_builder
app = backend_main.app
