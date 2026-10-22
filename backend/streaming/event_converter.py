"""LangGraph의 messages/updates 스트림을 화면용 이벤트로 바꿉니다."""

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from backend.schemas.stream import (
    DoneEvent,
    StreamEvent,
    TokenEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)


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
