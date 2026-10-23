"""동일 예시 기준 토큰 비교와 측정 불가 처리를 합성 trace로 검증합니다."""

import unittest
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from backend.eval.analyze_tokens import (
    TokenUsage,
    analyze,
    compare_usage,
    render_markdown,
    summarize_trace,
)


def run(*, run_type: str, parent_run_id=None, total_tokens=None, prompt_tokens=None,
        completion_tokens=None, model="gpt-4o", trace_id=None, reference_example_id=None,
        error=None, total_cost=None):
    return SimpleNamespace(
        id=uuid4(), run_type=run_type, parent_run_id=parent_run_id,
        trace_id=trace_id, reference_example_id=reference_example_id,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        total_tokens=total_tokens, total_cost=total_cost, error=error,
        extra={"invocation_params": {"model": model}} if model else {},
    )


def pair(example_id, total):
    root = run(run_type="chain", reference_example_id=example_id, total_tokens=total)
    root.trace_id = root.id
    llm = run(run_type="llm", parent_run_id=root.id, trace_id=root.id,
              total_tokens=total, prompt_tokens=total - 10, completion_tokens=10)
    return [root, llm]


class TokenAnalysisTests(unittest.TestCase):
    def test_only_descendant_llm_leaves_are_summed_once(self) -> None:
        root = run(run_type="chain", total_tokens=100, total_cost=Decimal("0.002"))
        child = run(run_type="chain", parent_run_id=root.id, total_tokens=100)
        first = run(run_type="llm", parent_run_id=child.id,
                    total_tokens=40, prompt_tokens=30, completion_tokens=10)
        second = run(run_type="llm", parent_run_id=root.id,
                     total_tokens=60, prompt_tokens=45, completion_tokens=15)
        unrelated = run(run_type="llm", total_tokens=900,
                        prompt_tokens=800, completion_tokens=100)

        usage = summarize_trace(root, [root, child, first, second, unrelated])

        self.assertEqual((usage.input_tokens, usage.output_tokens, usage.total_tokens), (75, 25, 100))
        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(usage.estimated_cost_usd, 0.002)

    def test_missing_or_zero_token_metadata_is_unavailable(self) -> None:
        root = run(run_type="chain")
        missing = run(run_type="llm", parent_run_id=root.id)
        self.assertIsNone(summarize_trace(root, [missing]).total_tokens)
        self.assertIn("누락", summarize_trace(root, [missing]).reason)

        zero = run(run_type="llm", parent_run_id=root.id,
                   total_tokens=0, prompt_tokens=0, completion_tokens=0)
        self.assertIsNone(summarize_trace(root, [zero]).total_tokens)
        self.assertIn("누락", summarize_trace(root, [zero]).reason)
        self.assertIn("하위 호출 없음", summarize_trace(root, []).reason)

    def test_parts_can_supply_missing_total_but_inconsistent_root_is_rejected(self) -> None:
        root = run(run_type="chain", total_tokens=12)
        llm = run(run_type="llm", parent_run_id=root.id,
                  prompt_tokens=9, completion_tokens=3)
        self.assertEqual(summarize_trace(root, [llm]).total_tokens, 12)
        root.total_tokens = 11
        self.assertIn("합계 불일치", summarize_trace(root, [llm]).reason)

    def test_total_without_input_output_still_scores_with_unknown_parts(self) -> None:
        root = run(run_type="chain", total_tokens=12)
        llm = run(run_type="llm", parent_run_id=root.id, total_tokens=12)

        usage = summarize_trace(root, [llm])

        self.assertEqual(usage.total_tokens, 12)
        self.assertIsNone(usage.input_tokens)
        self.assertIsNone(usage.output_tokens)
        self.assertIsNone(usage.reason)

    def test_greeting_and_complex_examples_each_use_own_baseline(self) -> None:
        greeting_id, complex_id = uuid4(), uuid4()
        baseline_runs = pair(greeting_id, 100) + pair(complex_id, 1000)
        candidate_runs = pair(greeting_id, 150) + pair(complex_id, 800)
        projects = {
            "base": SimpleNamespace(name="supervisor-v2", reference_dataset_id="same-dataset"),
            "current": SimpleNamespace(name="supervisor-v3", reference_dataset_id="same-dataset"),
        }

        class FakeClient:
            def read_project(self, *, project_id):
                return projects[project_id]

            def list_runs(self, *, project_id):
                return iter(baseline_runs if project_id == "base" else candidate_runs)

            def list_feedback(self, *, run_ids, feedback_key):
                self_feedback = [
                    SimpleNamespace(run_id=baseline_runs[0].id, key="response_quality", score=0.9),
                    SimpleNamespace(run_id=candidate_runs[0].id, key="response_quality", score=0.8),
                ]
                return (item for item in self_feedback if item.run_id in run_ids)

        baseline_name, candidate_name, dataset_id, rows = analyze(FakeClient(), "base", "current")
        by_id = {row.example_id: row for row in rows}

        self.assertEqual((baseline_name, candidate_name, dataset_id),
                         ("supervisor-v2", "supervisor-v3", "same-dataset"))
        self.assertAlmostEqual(by_id[str(greeting_id)].score, 2 / 3)
        self.assertEqual(by_id[str(complex_id)].score, 1.0)
        report = render_markdown(baseline_name, candidate_name, dataset_id, rows)
        self.assertIn("측정 가능: 2/2건", report)
        self.assertIn("0.90/0.80", report)
        self.assertIn("응답 품질 점수 하락", report)
        self.assertNotIn("안녕하세요", report)

    def test_different_models_and_missing_usage_do_not_get_zero_score(self) -> None:
        baseline = TokenUsage(80, 20, 100, 1, frozenset({"gpt-4o"}), None)
        other_model = TokenUsage(40, 10, 50, 1, frozenset({"other"}), None)
        missing = TokenUsage(None, None, None, 1, frozenset(), None, "토큰 누락")

        self.assertIsNone(compare_usage("example", baseline, other_model).score)
        self.assertIn("모델", compare_usage("example", baseline, other_model).reason)
        self.assertIsNone(compare_usage("example", baseline, missing).score)
        self.assertEqual(compare_usage("example", baseline, baseline).score, 1.0)

    def test_mismatched_datasets_are_rejected(self) -> None:
        class FakeClient:
            def read_project(self, *, project_id):
                return SimpleNamespace(name=project_id, reference_dataset_id=project_id)

        with self.assertRaisesRegex(ValueError, "Dataset"):
            analyze(FakeClient(), "first", "second")


if __name__ == "__main__":
    unittest.main()
