"""실측 요청이 독립 세션을 사용하고 실패를 숨기지 않는지 확인합니다."""

import unittest
from unittest.mock import AsyncMock

from backend.perf.benchmark import benchmark_request


class BenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_thread_per_request_and_task_counts(self) -> None:
        graph = AsyncMock()
        graph.ainvoke.return_value = {
            "tasks": [
                {"status": "completed"},
                {"status": "failed"},
                {"status": "completed"},
            ]
        }

        first = await benchmark_request(graph, "합성 질문", run_name="a31-test-1")
        await benchmark_request(graph, "합성 질문", run_name="a31-test-2")

        self.assertEqual(first["num_tasks"], 3)
        self.assertEqual(first["completed_tasks"], 2)
        self.assertEqual(first["failed_tasks"], 1)
        configs = [call.kwargs["config"] for call in graph.ainvoke.await_args_list]
        self.assertNotEqual(
            configs[0]["configurable"]["thread_id"],
            configs[1]["configurable"]["thread_id"],
        )

    async def test_request_error_is_recorded_without_internal_message(self) -> None:
        graph = AsyncMock()
        graph.ainvoke.side_effect = RuntimeError("private detail")

        result = await benchmark_request(graph, "합성 질문", run_name="a31-test")

        self.assertEqual(result["request_error"], "RuntimeError")
        self.assertNotIn("private detail", str(result))


if __name__ == "__main__":
    unittest.main()
