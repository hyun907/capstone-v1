"""LangSmith 연결 없이 기대 토픽 평가자의 점수와 누락값 처리를 확인합니다."""

import unittest
from types import SimpleNamespace

from backend.eval.evaluators import has_expected_topics


def evaluate(response: object, expected_topics: object) -> dict[str, str | float]:
    run = SimpleNamespace(outputs={"response": response})
    example = SimpleNamespace(outputs={"expected_topics": expected_topics})
    return has_expected_topics(run, example)


class HasExpectedTopicsTests(unittest.TestCase):
    def test_all_topics_found_ignoring_english_case(self) -> None:
        result = evaluate("DB 진단 후 복구 절차와 에스컬레이션을 진행합니다.", [
            "db 진단", "복구 절차", "에스컬레이션"
        ])

        self.assertEqual(result["key"], "has_expected_topics")
        self.assertEqual(result["score"], 1.0)
        self.assertIn("3/3", result["comment"])

    def test_partial_match_identifies_missing_topic(self) -> None:
        result = evaluate("시스템 상태는 정상입니다.", ["시스템 상태", "ticket 목록"])

        self.assertEqual(result["score"], 0.5)
        self.assertIn("ticket 목록", result["comment"])

    def test_database_alias_requires_standalone_db(self) -> None:
        self.assertEqual(evaluate("DB 장애를 진단합니다.", ["데이터베이스"])["score"], 1.0)
        self.assertEqual(evaluate("JDBC 연결을 진단합니다.", ["데이터베이스"])["score"], 0.0)

    def test_greeting_alias_covers_normal_reply(self) -> None:
        result = evaluate("안녕하세요. 무엇을 도와드릴까요?", ["인사"])

        self.assertEqual(result["score"], 1.0)

    def test_explicit_empty_expected_topics_passes_with_response(self) -> None:
        result = evaluate("안녕하세요.", [])

        self.assertEqual(result["score"], 1.0)
        self.assertIn("No expected topics", result["comment"])

    def test_missing_reference_does_not_pass(self) -> None:
        run = SimpleNamespace(outputs={"response": "답변"})
        example = SimpleNamespace(outputs=None)

        result = has_expected_topics(run, example)

        self.assertEqual(result["score"], 0.0)
        self.assertIn("missing or invalid", result["comment"])

    def test_empty_response_does_not_pass_even_without_expected_topics(self) -> None:
        result = evaluate("", [])

        self.assertEqual(result["score"], 0.0)
        self.assertIn("missing or empty", result["comment"])

    def test_invalid_reference_does_not_pass(self) -> None:
        result = evaluate("답변", [""])

        self.assertEqual(result["score"], 0.0)
        self.assertIn("missing or invalid", result["comment"])
