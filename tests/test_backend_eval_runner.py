"""Experiment 실행 설정과 불완전한 결과의 탐지를 검증합니다."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.eval.run_eval import run_evaluation, validate_rows


def result_row(*keys: str, run_error: str | None = None) -> dict:
    return {
        "run": SimpleNamespace(error=run_error, outputs={"response": "합성 답변"}),
        "evaluation_results": {
            "results": [SimpleNamespace(key=key, score=0.8) for key in keys]
        },
    }


class FakeExperimentResults:
    url = "https://smith.langchain.com/o/example/datasets/example/compare?selectedSessions=example"
    experiment_id = "example"

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    async def __aiter__(self):
        for row in self.rows:
            yield row


class EvalRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_five_examples_with_six_evaluators(self) -> None:
        keys = (
            "has_expected_topics", "response_quality", "task_structure",
            "plan_quality", "task_decomposition_quality", "expected_tool_calls",
        )
        rows = [result_row(*keys) for _ in range(5)]
        with patch.dict(os.environ, {"LANGSMITH_API_KEY": "fake", "OPENAI_API_KEY": "fake"}), patch(
            "backend.eval.run_eval.build_target", new=AsyncMock(return_value=object())
        ), patch(
            "backend.eval.run_eval.build_response_quality_judge", return_value=object()
        ), patch(
            "backend.eval.run_eval.build_plan_and_task_judges", return_value=(object(), object())
        ), patch(
            "backend.eval.run_eval.aevaluate",
            new=AsyncMock(return_value=FakeExperimentResults(rows)),
        ) as evaluate:
            location = await run_evaluation()

        self.assertEqual(location, FakeExperimentResults.url)
        self.assertEqual(evaluate.await_args.kwargs["data"], "capstone-ict-operations")
        self.assertEqual(evaluate.await_args.kwargs["max_concurrency"], 2)
        self.assertEqual(len(evaluate.await_args.kwargs["evaluators"]), 6)
        self.assertEqual(evaluate.await_args.kwargs["experiment_prefix"], "supervisor-v3")

    async def test_missing_key_stops_before_graph_build(self) -> None:
        with patch.dict(os.environ, {"LANGSMITH_API_KEY": ""}), patch(
            "backend.eval.run_eval.build_target", new=AsyncMock()
        ) as build:
            with self.assertRaisesRegex(RuntimeError, "LANGSMITH_API_KEY"):
                await run_evaluation()
        build.assert_not_awaited()

    def test_missing_score_is_failure(self) -> None:
        rows = [result_row("has_expected_topics", "response_quality", "task_structure", "plan_quality", "task_decomposition_quality") for _ in range(5)]
        with self.assertRaisesRegex(RuntimeError, "expected_tool_calls"):
            validate_rows(rows)

    def test_failed_run_is_failure(self) -> None:
        rows = [result_row("has_expected_topics", "response_quality", run_error="failed")]
        with self.assertRaisesRegex(RuntimeError, "Supervisor 실행"):
            validate_rows(rows)
