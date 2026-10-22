"""LangGraph의 messages/updates 스트림을 화면용 이벤트로 바꿉니다."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from openai import RateLimitError

from backend.schemas.stream import (
    DoneEvent,
    ErrorEvent,
    PlanCreatedEvent,
    StreamEvent,
    SubAgentTokenEvent,
    SubAgentToolCallEvent,
    TaskCompletedEvent,
    TaskListCreatedEvent,
    TaskStartedEvent,
    TokenEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)

logger = logging.getLogger(__name__)


async def convert_langgraph_events(
    langgraph_stream: AsyncIterator[tuple[str, Any]], thread_id: str
) -> AsyncIterator[StreamEvent]:
    """완성된 도구 인자는 updates에서, 답변 조각은 messages에서 읽습니다.

    도구 호출의 messages 조각에는 JSON 인자가 덜 만들어진 상태로 올 수 있어
    model 노드가 끝난 뒤의 updates에서 도구 시작 이벤트를 만듭니다.
    """
    tool_names: dict[str, str] = {}

    async for mode, data in langgraph_stream:
        if mode == "messages":
            message, _metadata = data
            if isinstance(message, (AIMessage, AIMessageChunk)) and message.text:
                yield TokenEvent(content=message.text)
        elif mode == "updates":
            for node_update in data.values():
                if not isinstance(node_update, dict):
                    continue
                for message in node_update.get("messages", []):
                    if isinstance(message, (AIMessage, AIMessageChunk)):
                        for call in message.tool_calls:
                            tool_names[call["id"]] = call["name"]
                            yield ToolCallStartEvent(
                                tool_name=call["name"], args=call.get("args", {})
                            )
                    elif isinstance(message, ToolMessage):
                        tool_name = message.name or tool_names.get(message.tool_call_id)
                        if tool_name:
                            yield ToolCallEndEvent(
                                tool_name=tool_name,
                                result=str(message.content)[:200],
                            )

    yield DoneEvent(thread_id=thread_id)


async def convert_supervisor_events(
    supervisor_stream: AsyncIterator[tuple], thread_id: str
) -> AsyncIterator[StreamEvent]:
    """Supervisor와 중첩 Sub-Agent 스트림을 Task ID가 있는 SSE 이벤트로 바꿉니다.

    호출자는 ``subgraphs=True``와 ``stream_mode=["messages", "updates"]``를 사용합니다.
    중첩 namespace의 execute_task 실행 ID를 현재 시작된 Task ID에 묶습니다.
    """
    previous_tasks: list[dict[str, Any]] = []
    active_task_id: str | None = None
    finalized = False
    namespace_tasks: dict[tuple[str, ...], str] = {}
    tool_calls: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}

    try:
        async for item in supervisor_stream:
            if len(item) == 3:
                namespace, mode, data = item
                namespace = tuple(namespace)
            else:
                mode, data = item
                namespace = ()

            task_id: str | None = None
            if namespace and namespace[0].startswith("execute_task:"):
                if namespace not in namespace_tasks and active_task_id:
                    namespace_tasks[namespace] = active_task_id
                task_id = namespace_tasks.get(namespace)

            if namespace:
                if not task_id:
                    continue
                if mode == "messages":
                    message, metadata = data
                    if (
                        isinstance(message, AIMessageChunk)
                        and metadata.get("langgraph_node") == "model"
                        and message.text
                    ):
                        yield SubAgentTokenEvent(task_id=task_id, content=message.text)
                elif mode == "updates":
                    for node_name, node_update in data.items():
                        if not isinstance(node_update, dict):
                            continue
                        for message in node_update.get("messages", []):
                            if node_name == "model" and isinstance(message, AIMessage):
                                for call in message.tool_calls:
                                    args = call.get("args", {})
                                    tool_calls[(task_id, call["id"])] = (call["name"], args)
                                    yield SubAgentToolCallEvent(
                                        task_id=task_id,
                                        tool_name=call["name"],
                                        args=args,
                                        status="start",
                                    )
                            elif node_name == "tools" and isinstance(message, ToolMessage):
                                call = tool_calls.pop((task_id, message.tool_call_id), None)
                                tool_name = message.name or (call[0] if call else None)
                                if tool_name:
                                    yield SubAgentToolCallEvent(
                                        task_id=task_id,
                                        tool_name=tool_name,
                                        args=call[1] if call else {},
                                        status="end",
                                        result=str(message.content)[:200],
                                    )
                continue

            if mode != "updates":
                # finalize의 완성 메시지도 messages 모드로 오므로 여기서는 사용하지 않습니다.
                continue
            for node_name, node_update in data.items():
                if not isinstance(node_update, dict):
                    continue
                if node_name == "planning":
                    yield PlanCreatedEvent(plan=node_update["plan"])
                    previous_tasks = node_update["tasks"]
                    yield TaskListCreatedEvent(tasks=previous_tasks)
                elif node_name == "start_task":
                    tasks = node_update["tasks"]
                    started = [
                        new for old, new in zip(previous_tasks, tasks)
                        if old["status"] == "pending" and new["status"] == "in_progress"
                    ]
                    if len(started) != 1:
                        raise ValueError("Supervisor 작업 시작 상태를 확인할 수 없습니다.")
                    active_task_id = started[0]["id"]
                    previous_tasks = tasks
                    yield TaskStartedEvent(
                        task_id=active_task_id, agent_name=started[0]["agent"]
                    )
                elif node_name == "execute_task":
                    tasks = node_update["tasks"]
                    completed = [
                        new for old, new in zip(previous_tasks, tasks)
                        if old["status"] == "in_progress" and new["status"] == "completed"
                    ]
                    if len(completed) != 1 or completed[0]["id"] != active_task_id:
                        raise ValueError("Supervisor 작업 완료 상태를 확인할 수 없습니다.")
                    previous_tasks = tasks
                    yield TaskCompletedEvent(
                        task_id=completed[0]["id"],
                        result_preview=(completed[0]["result"] or "")[:200],
                    )
                    active_task_id = None
                elif node_name == "finalize":
                    message = node_update["messages"][-1]
                    if not isinstance(message, AIMessage) or not message.text:
                        raise ValueError("Supervisor 최종 답변이 비어 있습니다.")
                    finalized = True
                    yield TokenEvent(content=message.text)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("Supervisor 스트림 변환 실패: %s", type(exc).__name__)
        if isinstance(exc, RateLimitError):
            if exc.code == "credit_balance_exhausted":
                yield ErrorEvent(
                    code="API_CREDIT_EXHAUSTED",
                    message="OpenAI API 크레딧이 소진되었습니다. API 결제 설정에서 잔액을 확인해 주세요.",
                )
            else:
                yield ErrorEvent(
                    code="MODEL_RATE_LIMIT",
                    message="OpenAI 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.",
                )
        else:
            yield ErrorEvent(
                code="STREAM_FAILED",
                message="응답 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            )
        return

    if not finalized or active_task_id:
        yield ErrorEvent(
            code="STREAM_FAILED",
            message="응답 생성이 완료되지 않았습니다. 다시 시도해 주세요.",
        )
        return
    yield DoneEvent(thread_id=thread_id)
