"""레이어 사이에서 전달하는 오류 데이터와 예외 타입."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ErrorLayer(str, Enum):
    DATA = "data_layer"
    TOOL = "tool_layer"
    ORCHESTRATION = "orchestration"
    APPLICATION = "application"
    PRESENTATION = "presentation"


class ErrorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ErrorRecoverability(str, Enum):
    RECOVERABLE = "recoverable"
    NON_RECOVERABLE = "non_recoverable"


class CapstoneError(BaseModel):
    """내부 원인과 사용자 안내를 분리한 오류 계약. 직접 raise하지 않습니다."""

    layer: ErrorLayer
    severity: ErrorSeverity
    recoverability: ErrorRecoverability
    code: str
    message: str
    user_message: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class CapstoneException(Exception):
    """Graph와 도구 경계에서 실제로 전파하는 예외."""

    def __init__(self, error: CapstoneError) -> None:
        self.error = error
        super().__init__(error.message)


class ToolError(CapstoneException):
    """MCP 도구 호출 또는 연결 실패."""


class OrchestrationError(CapstoneException):
    """계획 또는 응답 생성 실패."""
