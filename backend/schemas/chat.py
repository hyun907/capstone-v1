"""채팅 API의 요청·응답 데이터 계약."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """사용자가 보내는 채팅 요청."""

    message: str = Field(min_length=1, description="사용자의 자연어 메시지")
    thread_id: str | None = Field(default=None, min_length=1, description="대화 세션 식별자")

    @field_validator("message", "thread_id")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("빈 문자열이나 공백만 입력할 수 없습니다.")
        return value


class ChatResponse(BaseModel):
    """Agent가 반환하는 채팅 결과."""

    thread_id: str = Field(min_length=1, description="대화 세션 식별자")
    message: str = Field(min_length=1, description="Agent의 자연어 응답")
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list, description="Agent가 호출한 도구 목록"
    )

    @field_validator("thread_id", "message")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("빈 문자열이나 공백만 입력할 수 없습니다.")
        return value
