"""Reference Tool과 실제 호출 이름의 일치·누락·추가를 확인합니다."""

import unittest
from types import SimpleNamespace

from backend.eval.evaluators import expected_tool_calls


def evaluate(expected: object, actual: object) -> dict[str, str | float]:
    return expected_tool_calls(
        SimpleNamespace(outputs={"tools_used": actual}),
        SimpleNamespace(outputs={"expected_tools_used": expected}),
    )


class ExpectedToolCallsTests(unittest.TestCase):
    def test_exact_match_ignores_call_order_and_repeated_same_tool(self) -> None:
        result = evaluate(
            ["search_operations_manual", "search_jira_tickets"],
            ["search_jira_tickets", "search_operations_manual", "search_operations_manual"],
        )

        self.assertEqual(result["key"], "expected_tool_calls")
        self.assertEqual(result["score"], 1.0)
        self.assertIn("missing: []", result["comment"])

    def test_missing_required_tool_lowers_score_with_reason(self) -> None:
        result = evaluate(
            ["get_monitoring_status", "search_jira_tickets"],
            ["get_monitoring_status"],
        )

        self.assertAlmostEqual(result["score"], 2 / 3)
        self.assertIn("missing: ['search_jira_tickets']", result["comment"])

    def test_extra_tool_lowers_score_with_reason(self) -> None:
        result = evaluate(
            ["search_operations_manual"],
            ["search_operations_manual", "search_jira_tickets"],
        )

        self.assertAlmostEqual(result["score"], 2 / 3)
        self.assertIn("extra: ['search_jira_tickets']", result["comment"])

    def test_greeting_without_tools_passes_and_unneeded_call_fails(self) -> None:
        self.assertEqual(evaluate([], [])["score"], 1.0)
        result = evaluate([], ["search_operations_manual"])
        self.assertEqual(result["score"], 0.0)
        self.assertIn("extra: ['search_operations_manual']", result["comment"])

    def test_missing_record_is_not_treated_as_no_calls(self) -> None:
        self.assertEqual(evaluate([], None)["score"], 0.0)
        self.assertEqual(evaluate(None, [])["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
