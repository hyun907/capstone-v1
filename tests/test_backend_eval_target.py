"""Eval target의 직접 호출과 예시별 세션 분리를 검증합니다."""

import unittest
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage

from backend.eval.target import make_target


class EvalTargetTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_supervisor_result_with_fresh_thread_for_each_example(self) -> None:
        graph = AsyncMock()
        graph.ainvoke.return_value = {
            "messages": [AIMessage(content="진단 후 복구합니다.")],
            "plan": "상태를 확인하고 답변합니다.",
            "tasks": [{"id": "task_1", "agent": "writing", "status": "completed"}],
        }
        target_function = make_target(graph)

        first = await target_function({"message": "첫 질문"})
        second = await target_function({"message": "둘째 질문"})

        self.assertEqual(first["response"], "진단 후 복구합니다.")
        self.assertEqual(first["plan"], "상태를 확인하고 답변합니다.")
        self.assertEqual(first["tasks"][0]["id"], "task_1")
        self.assertEqual(second, first)
        first_call, second_call = graph.ainvoke.await_args_list
        self.assertEqual(first_call.args[0]["messages"][0].content, "첫 질문")
        self.assertEqual(second_call.args[0]["messages"][0].content, "둘째 질문")
        first_thread = first_call.kwargs["config"]["configurable"]["thread_id"]
        second_thread = second_call.kwargs["config"]["configurable"]["thread_id"]
        self.assertNotEqual(first_thread, second_thread)

    async def test_rejects_bad_input_before_calling_graph(self) -> None:
        graph = AsyncMock()
        with self.assertRaisesRegex(ValueError, "message"):
            await make_target(graph)({"message": "  "})
        graph.ainvoke.assert_not_awaited()

    async def test_rejects_missing_final_answer(self) -> None:
        graph = AsyncMock()
        graph.ainvoke.return_value = {
            "messages": [AIMessage(content="  ")],
            "plan": "계획",
            "tasks": [{"id": "task_1"}],
        }
        with self.assertRaisesRegex(ValueError, "최종 답변"):
            await make_target(graph)({"message": "질문"})
