"""MCP 도구의 응답 데이터 계약."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SystemStatus(BaseModel):
    """모니터링 시스템 상태 조회 결과."""

    system_name: str = Field(min_length=1, description="시스템 이름")
    status: Literal["healthy", "degraded", "down", "unknown"] = Field(
        description="시스템 상태"
    )
    cpu_percent: float = Field(ge=0, le=100, description="CPU 사용률 (%)")
    memory_percent: float = Field(ge=0, le=100, description="메모리 사용률 (%)")
    last_checked: datetime = Field(description="마지막 확인 시각 (ISO 8601)")
    alerts: list[str] = Field(default_factory=list, description="활성 알림 목록")


class ManualSnippet(BaseModel):
    """운영 매뉴얼 검색 결과의 단일 항목."""

    title: str = Field(min_length=1, description="문서 제목")
    source: str = Field(min_length=1, description="문서 URI")
    snippet: str = Field(description="검색 본문 일부")
    score: float = Field(ge=0, description="검색 점수")


class JiraTicket(BaseModel):
    """Jira 티켓 검색 결과의 단일 항목."""

    key: str = Field(min_length=1, description="티켓 키")
    status: str = Field(min_length=1, description="현재 상태")
    summary: str = Field(min_length=1, description="요약")
    priority: str = Field(min_length=1, description="우선순위")
    updated: datetime = Field(description="마지막 갱신 시각 (ISO 8601)")
    assignee: str | None = Field(default=None, description="담당자 이메일")


class JiraTicketCreated(BaseModel):
    """Jira 티켓 생성 결과."""

    key: str = Field(min_length=1, description="생성된 티켓 키")
    url: str = Field(min_length=1, description="티켓 조회 URL")
    summary: str = Field(min_length=1, description="제목")
    status: str = Field(min_length=1, description="생성 시점의 상태 (API 응답에 없으면 Unknown)")
    created_at: datetime = Field(description="생성 결과를 확인한 시각 (ISO 8601)")
