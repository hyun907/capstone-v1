"""단일 Agent와 Supervisor의 진행 상황을 전달하는 SSE 이벤트 계약."""

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


class PlanCreatedEvent(StreamEvent):
    type: Literal["plan_created"] = "plan_created"
    plan: str


class TaskListCreatedEvent(StreamEvent):
    type: Literal["task_list_created"] = "task_list_created"
    tasks: list[dict[str, Any]]


class TaskStartedEvent(StreamEvent):
    type: Literal["task_started"] = "task_started"
    task_id: str
    agent_name: Literal["research", "writing"]


class TaskCompletedEvent(StreamEvent):
    type: Literal["task_completed"] = "task_completed"
    task_id: str
    result_preview: str | None = None


class SubAgentTokenEvent(StreamEvent):
    type: Literal["sub_agent_token"] = "sub_agent_token"
    task_id: str
    content: str


class SubAgentToolCallEvent(StreamEvent):
    type: Literal["sub_agent_tool_call"] = "sub_agent_tool_call"
    task_id: str
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: Literal["start", "end"]
    result: str | None = None
