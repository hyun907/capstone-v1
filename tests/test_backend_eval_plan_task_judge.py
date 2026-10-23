"""계획과 Task Judge의 입력 분리 및 점수 계약을 확인합니다."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError

from backend.eval.judge import make_plan_quality_judge, make_task_decomposition_judge


class PlanTaskJudgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_judge_scores_question_and_plan_without_task_results(self) -> None:
        judge = AsyncMock()
        judge.ainvoke.return_value = {"score": 0.9, "reasoning": "두 요구를 계획에 반영했다."}
        evaluator = make_plan_quality_judge(judge)

        result = await evaluator(
            SimpleNamespace(outputs={"plan": "DB 절차와 관련 티켓을 확인한다.", "tasks": [{"result": "비공개 실행 결과"}]}),
            SimpleNamespace(inputs={"message": "DB 절차와 관련 티켓을 알려주세요."}),
        )

        self.assertEqual(result, {
            "key": "plan_quality", "score": 0.9, "comment": "두 요구를 계획에 반영했다.",
        })
        prompt = judge.ainvoke.await_args.args[0][1].content
        self.assertIn("DB 절차와 관련 티켓", prompt)
        self.assertNotIn("비공개 실행 결과", prompt)

    async def test_task_judge_only_sees_planned_roles_and_descriptions(self) -> None:
        judge = AsyncMock()
        judge.ainvoke.return_value = {"score": 0.4, "reasoning": "조사 작업이 의미상 겹친다."}
        evaluator = make_task_decomposition_judge(judge)

        result = await evaluator(
            SimpleNamespace(outputs={"tasks": [
                {"agent": "research", "description": "DB 절차 조회", "status": "completed", "result": "비공개 실행 결과"},
                {"agent": "writing", "description": "답변 작성", "status": "pending", "result": None},
            ]}),
            SimpleNamespace(inputs={"message": "DB 절차는?"}),
        )

        self.assertEqual(result["key"], "task_decomposition_quality")
        self.assertEqual(result["score"], 0.4)
        self.assertIn("겹친다", result["comment"])
        prompt = judge.ainvoke.await_args.args[0][1].content
        self.assertIn("DB 절차 조회", prompt)
        self.assertNotIn("completed", prompt)
        self.assertNotIn("비공개 실행 결과", prompt)
        self.assertIn("Research가 없다는 이유로 감점하지", judge.ainvoke.await_args.args[0][0].content)

    async def test_missing_plan_or_tasks_never_calls_judge(self) -> None:
        judge = AsyncMock()

        with self.assertRaisesRegex(ValueError, "계획"):
            await make_plan_quality_judge(judge)(
                SimpleNamespace(outputs={"plan": ""}),
                SimpleNamespace(inputs={"message": "질문"}),
            )
        with self.assertRaisesRegex(ValueError, "Task"):
            await make_task_decomposition_judge(judge)(
                SimpleNamespace(outputs={"tasks": []}),
                SimpleNamespace(inputs={"message": "질문"}),
            )
        judge.ainvoke.assert_not_awaited()

    async def test_out_of_range_judge_score_is_rejected(self) -> None:
        judge = AsyncMock()
        judge.ainvoke.return_value = {"score": -0.1, "reasoning": "잘못된 점수"}

        with self.assertRaises(ValidationError):
            await make_plan_quality_judge(judge)(
                SimpleNamespace(outputs={"plan": "답변을 준비한다."}),
                SimpleNamespace(inputs={"message": "질문"}),
            )


if __name__ == "__main__":
    unittest.main()
