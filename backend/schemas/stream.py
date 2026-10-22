"""단일 Agent의 진행 상황을 전달하는 SSE 이벤트 계약."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class StreamEvent(BaseModel):
    type: str


class TokenEvent(StreamEvent):
    type: Literal["token"] = "token"
    content: str


class ToolCallStartEvent(StreamEvent):
    type: Literal["tool_call_start"] = "tool_call_start"
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolCallEndEvent(StreamEvent):
    type: Literal["tool_call_end"] = "tool_call_end"
    tool_name: str
    result: str | None = None


class DoneEvent(StreamEvent):
    type: Literal["done"] = "done"
    thread_id: str


class ErrorEvent(StreamEvent):
    type: Literal["error"] = "error"
    code: Literal["API_CREDIT_EXHAUSTED", "MODEL_RATE_LIMIT", "STREAM_FAILED"]
    message: str
