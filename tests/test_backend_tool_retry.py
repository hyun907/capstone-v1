"""읽기 도구 재시도와 Agent까지의 오류 전파를 합성 도구로 검증합니다."""

import unittest
from unittest.mock import AsyncMock, patch

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import StructuredTool

from backend.agent.graph import build_agent
from backend.agent.mcp_client import wrap_mcp_tool
from backend.agent.supervisor_graph import build_supervisor_graph
from backend.error_handling.retry import with_retry
from backend.schemas.error import ToolError
from tests.test_backend_agent_graph import (
    SyntheticChatModel,
    search_jira_tickets,
    search_operations_manual,
)
from tests.test_backend_supervisor_execution import plan


class ToolRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_timeouts_then_success_waits_half_and_one_point_five(self) -> None:
        calls = 0

        async def work() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise TimeoutError("internal detail")
            return "synthetic result"

        with patch("backend.error_handling.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
            self.assertEqual(await with_retry(work, tool_name="test"), "synthetic result")
        self.assertEqual(calls, 3)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [0.5, 1.5])

    async def test_three_timeouts_become_tool_error(self) -> None:
        work = AsyncMock(side_effect=TimeoutError("private-token"))
        with patch("backend.error_handling.retry.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ToolError) as caught:
                await with_retry(work, tool_name="synthetic")
        self.assertEqual(work.await_count, 3)
        self.assertEqual(caught.exception.error.code, "TOOL_TIMEOUT_AFTER_RETRY")
        self.assertNotIn("private-token", caught.exception.error.user_message)

    async def test_non_timeout_fails_without_retry(self) -> None:
        work = AsyncMock(side_effect=RuntimeError("private-token"))
        with patch("backend.error_handling.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
            with self.assertRaises(ToolError) as caught:
                await with_retry(work, tool_name="synthetic")
        work.assert_awaited_once()
        sleep.assert_not_awaited()
        self.assertEqual(caught.exception.error.code, "TOOL_EXECUTION_ERROR")

    async def test_wrapped_tool_error_reaches_agent_caller(self) -> None:
        async def failing_status(system_name: str) -> str:
            raise RuntimeError("private-token")

        status = StructuredTool.from_function(
            coroutine=failing_status,
            name="get_monitoring_status",
            description="합성 시스템 상태 조회",
        )
        wrap_mcp_tool(status)
        agent = await build_agent(
            model=SyntheticChatModel(),
            tools=[status, search_operations_manual, search_jira_tickets],
        )
        with self.assertRaises(ToolError) as caught:
            await agent.ainvoke(
                {"messages": [{"role": "user", "content": "상태 확인"}]},
                {"configurable": {"thread_id": "tool-error-propagation"}},
            )
        self.assertEqual(caught.exception.error.code, "TOOL_EXECUTION_ERROR")
        self.assertNotIn("private-token", caught.exception.error.user_message)

    async def test_wrapped_tool_error_is_caught_by_supervisor_task(self) -> None:
        async def failing_status(system_name: str) -> str:
            raise RuntimeError("private-token")

        status = wrap_mcp_tool(StructuredTool.from_function(
            coroutine=failing_status,
            name="get_monitoring_status",
            description="합성 시스템 상태 조회",
        ))
        research = create_agent(
            model=SyntheticChatModel(always_call_tool=True),
            tools=[status],
        )
        graph = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: plan("research", "writing")),
            research_agent=research,
            writing_agent=RunnableLambda(
                lambda _: {"messages": [AIMessage(content="합성 답변")]}
            ),
        )
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "상태 확인"}]},
            {"configurable": {"thread_id": "tool-supervisor-propagation"}},
        )
        self.assertEqual(result["tasks"][0]["status"], "failed")
        self.assertEqual(result["tasks"][0]["error_code"], "TOOL_EXECUTION_ERROR")
        self.assertEqual(result["tasks"][1]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
