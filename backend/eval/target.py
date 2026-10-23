"""LangSmith 평가에서 Supervisor를 HTTP 없이 실행하는 Target."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import UUID, uuid4

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from backend.agent.supervisor_graph import build_supervisor_graph


class ToolCallRecorder(AsyncCallbackHandler):
    """Tool 시작 이벤트의 이름만 보관하고 인자와 결과는 보관하지 않습니다."""

    def __init__(self) -> None:
        self.names: list[str] = []

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = kwargs.get("name") or serialized.get("name")
        self.names.append(name if isinstance(name, str) and name else "<unnamed>")


def make_target(graph: Runnable) -> Callable[[Mapping[str, object]], Awaitable[dict[str, Any]]]:
    """그래프를 재사용하면서 평가 예시마다 독립된 대화 스레드를 만듭니다."""

    async def target_function(inputs: Mapping[str, object]) -> dict[str, Any]:
        message = inputs.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("평가 입력에는 비어 있지 않은 message가 필요합니다.")

        recorder = ToolCallRecorder()
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": str(uuid4())}, "callbacks": [recorder]},
        )
        if not isinstance(result, dict):
            raise ValueError("Supervisor가 상태를 반환하지 않았습니다.")

        messages = result.get("messages")
        final_message = messages[-1] if isinstance(messages, list) and messages else None
        if (
            not isinstance(final_message, AIMessage)
            or not isinstance(final_message.content, str)
            or not final_message.content.strip()
        ):
            raise ValueError("Supervisor의 최종 답변이 없거나 텍스트가 아닙니다.")

        plan = result.get("plan")
        tasks = result.get("tasks")
        if not isinstance(plan, str) or not plan.strip():
            raise ValueError("Supervisor의 계획이 없습니다.")
        if not isinstance(tasks, list) or not tasks:
            raise ValueError("Supervisor의 Task 목록이 없습니다.")

        return {
            "response": final_message.content,
            "plan": plan,
            "tasks": tasks,
            "tools_used": recorder.names,
        }

    return target_function


async def build_target() -> Callable[[Mapping[str, object]], Awaitable[dict[str, Any]]]:
    """실서비스와 같은 Supervisor 그래프를 한 번 준비합니다."""
    return make_target(await build_supervisor_graph())
