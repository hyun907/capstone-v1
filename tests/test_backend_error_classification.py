"""공통 오류 분류는 내부 원인을 사용자 메시지에 노출하지 않아야 합니다."""

import asyncio
import unittest

import httpx
from openai import RateLimitError

from backend.error_handling.classification import classify_exception
from backend.schemas.error import (
    CapstoneError,
    ErrorLayer,
    ErrorRecoverability,
    ErrorSeverity,
    ToolError,
)


class ErrorClassificationTests(unittest.TestCase):
    def test_tool_timeout_and_execution_failure_are_distinct(self) -> None:
        for exc, code in (
            (asyncio.TimeoutError("private-token"), "TOOL_TIMEOUT"),
            (RuntimeError("private-token"), "TOOL_EXECUTION_ERROR"),
        ):
            with self.subTest(code=code):
                error = classify_exception(exc, layer=ErrorLayer.TOOL)
                self.assertEqual(error.code, code)
                self.assertEqual(error.recoverability, ErrorRecoverability.RECOVERABLE)
                self.assertIn("private-token", error.message)
                self.assertNotIn("private-token", error.user_message)

    def test_planning_response_and_stream_failures(self) -> None:
        cases = (
            (ErrorLayer.ORCHESTRATION, "planning", "PLANNING_FAILED"),
            (ErrorLayer.ORCHESTRATION, "response", "RESPONSE_FAILED"),
            (ErrorLayer.APPLICATION, "stream", "STREAM_FAILED"),
        )
        for layer, operation, code in cases:
            with self.subTest(code=code):
                error = classify_exception(
                    ValueError("private-token"), layer=layer, operation=operation
                )
                self.assertEqual(error.code, code)
                self.assertNotIn("private-token", error.user_message)

    def test_existing_rate_limit_codes_remain_compatible(self) -> None:
        response = httpx.Response(
            429,
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        )
        for body, code in ((None, "MODEL_RATE_LIMIT"), ({"code": "credit_balance_exhausted"}, "API_CREDIT_EXHAUSTED")):
            with self.subTest(code=code):
                exc = RateLimitError("private-token", response=response, body=body)
                error = classify_exception(exc, layer=ErrorLayer.APPLICATION)
                self.assertEqual(error.code, code)
                self.assertNotIn("private-token", error.user_message)

    def test_wrapped_tool_error_preserves_safe_model(self) -> None:
        error = CapstoneError(
            layer=ErrorLayer.TOOL,
            severity=ErrorSeverity.MEDIUM,
            recoverability=ErrorRecoverability.RECOVERABLE,
            code="TOOL_TIMEOUT",
            message="private-token",
            user_message="도구 응답이 지연되었습니다.",
        )
        wrapped = ToolError(error)
        self.assertIs(classify_exception(wrapped, layer=ErrorLayer.ORCHESTRATION), error)
        self.assertEqual(str(wrapped), "private-token")


if __name__ == "__main__":
    unittest.main()
