"""계획 단계의 Task 구조 규칙을 합성 사례로 확인합니다."""

import unittest
from types import SimpleNamespace

from backend.eval.evaluators import task_structure


def task(agent: str, description: str, **execution_fields: object) -> dict[str, object]:
    return {"agent": agent, "description": description, **execution_fields}


def evaluate(question: str, tasks: object) -> dict[str, str | float]:
    return task_structure(
        SimpleNamespace(outputs={"tasks": tasks}),
        SimpleNamespace(inputs={"message": question}),
    )


class TaskStructureTests(unittest.TestCase):
    def test_valid_research_then_writing_ignores_execution_status(self) -> None:
        tasks = [
            task("research", "DB 절차 조회", status="completed", result="민감한 실행 결과"),
            task("research", "관련 티켓 조회", status="pending", result=None),
            task("writing", "두 결과를 통합", status="in_progress", result=None),
        ]

        result = evaluate("DB 절차와 티켓을 알려주세요.", tasks)

        self.assertEqual(result["score"], 1.0)
        self.assertNotIn("민감한 실행 결과", result["comment"])

    def test_duplicate_research_description_fails_even_with_spacing_difference(self) -> None:
        result = evaluate("DB 절차를 알려주세요.", [
            task("research", "DB   절차 조회"),
            task("research", "db 절차 조회"),
            task("writing", "정리"),
        ])

        self.assertEqual(result["score"], 0.0)
        self.assertIn("Duplicate Research", result["comment"])

    def test_simple_greeting_with_unnecessary_research_fails(self) -> None:
        result = evaluate("안녕하세요.", [
            task("research", "인사말 조회"), task("writing", "인사"),
        ])

        self.assertEqual(result["score"], 0.0)
        self.assertIn("Simple greeting", result["comment"])
        self.assertEqual(evaluate("안녕하세요, DB 상태는?", [
            task("research", "DB 상태 조회"), task("writing", "상태 전달"),
        ])["score"], 1.0)

    def test_missing_or_bad_task_structure_fails(self) -> None:
        self.assertEqual(evaluate("질문", [])["score"], 0.0)
        self.assertEqual(evaluate("질문", [task("research", "조회")])["score"], 0.0)
        self.assertEqual(evaluate("질문", [task("writing", "정리"), task("writing", "추가")])["score"], 0.0)
        self.assertEqual(evaluate("질문", [task("writing", "정리")] * 7)["score"], 0.0)
        self.assertEqual(evaluate("질문", [task("writing", " ")])["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
