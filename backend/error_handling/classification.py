"""예외를 사용자에게 안전한 공통 오류 계약으로 분류합니다."""

import asyncio
from typing import Literal

from openai import RateLimitError

from backend.schemas.error import (
    CapstoneError,
    CapstoneException,
    ErrorLayer,
    ErrorRecoverability,
    ErrorSeverity,
)

Operation = Literal["planning", "response", "stream"]

_USER_MESSAGES = {
    "TOOL_TIMEOUT": "도구 응답이 지연되었습니다. 일부 정보를 확인하지 못했습니다.",
    "TOOL_EXECUTION_ERROR": "도구 사용 중 문제가 발생했습니다. 일부 정보를 확인하지 못했습니다.",
    "PLANNING_FAILED": "요청을 처리할 계획을 만들지 못했습니다. 다시 시도해 주세요.",
    "RESPONSE_FAILED": "응답을 생성하지 못했습니다. 다시 시도해 주세요.",
    "AGENT_FAILED": "작업을 처리하는 중 문제가 발생했습니다. 다시 시도해 주세요.",
    "API_CREDIT_EXHAUSTED": "OpenAI API 크레딧이 소진되었습니다. API 결제 설정에서 잔액을 확인해 주세요.",
    "MODEL_RATE_LIMIT": "OpenAI 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.",
    "STREAM_FAILED": "응답 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "DATA_UNAVAILABLE": "필요한 데이터를 확인하지 못했습니다. 다시 시도해 주세요.",
    "PRESENTATION_FAILED": "화면에 결과를 표시하지 못했습니다. 다시 시도해 주세요.",
}


def classify_exception(
    exc: Exception,
    *,
    layer: ErrorLayer,
    operation: Operation | None = None,
    context: dict[str, str] | None = None,
) -> CapstoneError:
    """원본 예외 문자열은 내부 필드에만 보관하고 고정된 안내문을 반환합니다."""
    if isinstance(exc, CapstoneException):
        return exc.error

    if isinstance(exc, RateLimitError):
        code = (
            "API_CREDIT_EXHAUSTED"
            if exc.code == "credit_balance_exhausted"
            else "MODEL_RATE_LIMIT"
        )
        severity = ErrorSeverity.HIGH if code == "API_CREDIT_EXHAUSTED" else ErrorSeverity.MEDIUM
        recoverability = ErrorRecoverability.NON_RECOVERABLE
    elif layer == ErrorLayer.TOOL:
        code = "TOOL_TIMEOUT" if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) else "TOOL_EXECUTION_ERROR"
        severity = ErrorSeverity.MEDIUM
        recoverability = ErrorRecoverability.RECOVERABLE
    elif layer == ErrorLayer.ORCHESTRATION:
        code = {"planning": "PLANNING_FAILED", "response": "RESPONSE_FAILED"}.get(
            operation, "AGENT_FAILED"
        )
        severity = ErrorSeverity.MEDIUM
        recoverability = ErrorRecoverability.RECOVERABLE
    elif layer == ErrorLayer.DATA:
        code = "DATA_UNAVAILABLE"
        severity = ErrorSeverity.MEDIUM
        recoverability = ErrorRecoverability.RECOVERABLE
    elif layer == ErrorLayer.PRESENTATION:
        code = "PRESENTATION_FAILED"
        severity = ErrorSeverity.MEDIUM
        recoverability = ErrorRecoverability.NON_RECOVERABLE
    else:
        code = "STREAM_FAILED"
        severity = ErrorSeverity.HIGH
        recoverability = ErrorRecoverability.NON_RECOVERABLE

    return CapstoneError(
        layer=layer,
        severity=severity,
        recoverability=recoverability,
        code=code,
        message=f"{type(exc).__name__}: {exc}",
        user_message=_USER_MESSAGES[code],
        context=context or {},
    )
