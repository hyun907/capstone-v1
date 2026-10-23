"""응답 품질 Judge의 입력과 결과 계약을 외부 API 없이 확인합니다."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError

from backend.eval.judge import make_response_quality_judge


class ResponseQualityJudgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_score_and_reasoning(self) -> None:
        judge = AsyncMock()
        judge.ainvoke.return_value = {"score": 0.8, "reasoning": "질문에 답하고 한계를 밝혔다."}
        evaluator = make_response_quality_judge(judge)

        result = await evaluator(
            SimpleNamespace(outputs={"response": "장애 원인을 먼저 확인하세요."}),
            SimpleNamespace(inputs={"message": "DB 장애 시 무엇을 하나요?"}),
        )

        self.assertEqual(
            result,
            {
                "key": "response_quality",
                "score": 0.8,
                "comment": "질문에 답하고 한계를 밝혔다.",
            },
        )
        messages = judge.ainvoke.await_args.args[0]
        self.assertIn("DB 장애", messages[1].content)
        self.assertIn("장애 원인", messages[1].content)

    async def test_invalid_score_is_not_saved_as_valid_feedback(self) -> None:
        judge = AsyncMock()
        judge.ainvoke.return_value = {"score": 1.4, "reasoning": "범위 밖 점수"}
        evaluator = make_response_quality_judge(judge)

        with self.assertRaises(ValidationError):
            await evaluator(
                SimpleNamespace(outputs={"response": "답변"}),
                SimpleNamespace(inputs={"message": "질문"}),
            )

    async def test_missing_response_does_not_call_model(self) -> None:
        judge = AsyncMock()
        evaluator = make_response_quality_judge(judge)

        with self.assertRaisesRegex(ValueError, "최종 응답"):
            await evaluator(
                SimpleNamespace(outputs={"response": "  "}),
                SimpleNamespace(inputs={"message": "질문"}),
            )
        judge.ainvoke.assert_not_awaited()

    async def test_model_error_is_propagated(self) -> None:
        judge = AsyncMock()
        judge.ainvoke.side_effect = RuntimeError("synthetic judge failure")
        evaluator = make_response_quality_judge(judge)

        with self.assertRaisesRegex(RuntimeError, "synthetic judge failure"):
            await evaluator(
                SimpleNamespace(outputs={"response": "답변"}),
                SimpleNamespace(inputs={"message": "질문"}),
            )
