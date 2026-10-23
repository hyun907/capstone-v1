"""합성 Sub-Agent로 Supervisor 병렬 실행, 상태 전환, 실패를 확인합니다."""

import asyncio
import unittest
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool

from backend.agent.supervisor_graph import build_supervisor_graph
from backend.error_handling.classification import classify_exception
from backend.schemas.error import ErrorLayer, ToolError


def plan(*agents: str) -> dict:
    return {
        "plan": "필요한 자료를 확인하고 답변합니다.",
        "tasks": [
            {"description": f"{agent} 작업 {index}", "agent": agent}
            for index, agent in enumerate(agents, start=1)
        ],
    }


class SupervisorExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_research_runs_concurrently_and_writing_receives_all_results(self) -> None:
        calls = []
        started = set()
        both_started = asyncio.Event()

        async def research(request):
            content = request["messages"][-1].content
            task_number = "1" if "research 작업 1" in content else "2"
            started.add(task_number)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1)
            calls.append(("research", content))
            return {"messages": [AIMessage(content=f"조회 결과 {task_number}")]}

        def writing(request):
            calls.append(("writing", request["messages"][-1].content))
            return {"messages": [AIMessage(content="두 결과를 통합한 답변")]}

        graph = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: plan("research", "research", "writing")),
            research_agent=RunnableLambda(research),
            writing_agent=RunnableLambda(writing),
        )
        config = {"configurable": {"thread_id": "supervisor-execution"}}
        updates = []
        async for update in graph.astream(
            {"messages": [{"role": "user", "content": "DB와 네트워크를 비교해 주세요"}]},
            config,
            stream_mode="updates",
        ):
            updates.append(update)

        self.assertEqual(
            [next(iter(update)) for update in updates],
            ["planning", "execute_research", "execute_writing", "finalize"],
        )
        self.assertEqual(
            [task["status"] for task in updates[1]["execute_research"]["tasks"]],
            ["completed", "completed", "pending"],
        )
        self.assertEqual(
            [task["status"] for task in updates[2]["execute_writing"]["tasks"]],
            ["completed"] * 3,
        )
        self.assertEqual(started, {"1", "2"})
        self.assertEqual([name for name, _ in calls], ["research", "research", "writing"])
        self.assertIn("DB와 네트워크를 비교해 주세요", calls[-1][1])
        self.assertIn("조회 결과 1", calls[-1][1])
        self.assertIn("조회 결과 2", calls[-1][1])
        final = (await graph.aget_state(config)).values
        self.assertEqual(final["current_task_index"], 3)
        self.assertEqual(final["messages"][-1].content, "두 결과를 통합한 답변")

    async def test_followup_replans_and_agent_failures_return_fallback(self) -> None:
        def planner(messages):
            users = [message for message in messages if isinstance(message, HumanMessage)]
            return plan("research", "writing") if len(users) == 1 else plan("writing")

        graph = await build_supervisor_graph(
            planner=RunnableLambda(planner),
            research_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="조회 결과")]}),
            writing_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="답변")]}),
        )
        config = {"configurable": {"thread_id": "supervisor-followup"}}
        first = await graph.ainvoke({"messages": [{"role": "user", "content": "첫 질문"}]}, config)
        second = await graph.ainvoke({"messages": [{"role": "user", "content": "후속 질문"}]}, config)
        self.assertEqual([task["agent"] for task in first["tasks"]], ["research", "writing"])
        self.assertEqual([task["agent"] for task in second["tasks"]], ["writing"])
        self.assertEqual(second["current_task_index"], 1)
        self.assertEqual(len(second["messages"]), 4)

        def failed_research(_):
            raise RuntimeError("합성 도구 실패")

        failed = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: plan("research", "writing")),
            research_agent=RunnableLambda(failed_research),
            writing_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="답변")]}),
        )
        failed_result = await failed.ainvoke(
            {"messages": [{"role": "user", "content": "실패 질문"}]},
            {"configurable": {"thread_id": "supervisor-failure"}},
        )
        self.assertEqual([task["status"] for task in failed_result["tasks"]], ["failed", "completed"])
        self.assertIn("일부 정보 수집에 실패", failed_result["messages"][-1].content)
        self.assertNotIn("합성 도구 실패", failed_result["messages"][-1].content)

        empty = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: plan("writing")),
            research_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="조회 결과")]}),
            writing_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="   ")]}),
        )
        empty_result = await empty.ainvoke(
            {"messages": [{"role": "user", "content": "빈 답변 질문"}]},
            {"configurable": {"thread_id": "supervisor-empty"}},
        )
        self.assertEqual(empty_result["tasks"][0]["status"], "failed")
        self.assertTrue(empty_result["messages"][-1].content.strip())

    async def test_tool_failure_keeps_later_research_and_writing(self) -> None:
        calls = 0
        writing_requests = []

        def research(_):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ToolError(classify_exception(
                    RuntimeError("private-token"), layer=ErrorLayer.TOOL
                ))
            return {"messages": [AIMessage(content="두 번째 합성 조회 결과")]}

        def writing(request):
            writing_requests.append(request["messages"][-1].content)
            return {"messages": [AIMessage(content="확인된 자료로 답변합니다.")]}

        graph = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: plan("research", "research", "writing")),
            research_agent=RunnableLambda(research),
            writing_agent=RunnableLambda(writing),
        )
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "합성 질문"}]},
            {"configurable": {"thread_id": "supervisor-partial-success"}},
        )
        self.assertEqual([task["status"] for task in result["tasks"]],
                         ["failed", "completed", "completed"])
        self.assertEqual(result["current_task_index"], 3)
        self.assertEqual(result["tasks"][0]["error_code"], "TOOL_EXECUTION_ERROR")
        self.assertIn("두 번째 합성 조회 결과", writing_requests[0])
        self.assertIn("실패한 Research 작업", writing_requests[0])
        self.assertNotIn("private-token", writing_requests[0])
        self.assertIn("일부 정보 수집에 실패", result["messages"][-1].content)

    async def test_writing_failure_returns_partial_result(self) -> None:
        graph = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: plan("research", "writing")),
            research_agent=RunnableLambda(
                lambda _: {"messages": [AIMessage(content="합성 수집 자료")]}
            ),
            writing_agent=RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("private-token"))),
        )
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "합성 질문"}]},
            {"configurable": {"thread_id": "supervisor-writing-failure"}},
        )
        self.assertEqual([task["status"] for task in result["tasks"]], ["completed", "failed"])
        self.assertIn("합성 수집 자료", result["messages"][-1].content)
        self.assertNotIn("private-token", result["messages"][-1].content)

    async def test_no_successful_task_still_returns_nonempty_response(self) -> None:
        def failed_agent(_):
            raise RuntimeError("private-token")

        graph = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: plan("research", "writing")),
            research_agent=RunnableLambda(failed_agent),
            writing_agent=RunnableLambda(failed_agent),
        )
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "합성 질문"}]},
            {"configurable": {"thread_id": "supervisor-no-results"}},
        )
        self.assertEqual([task["status"] for task in result["tasks"]], ["failed", "failed"])
        self.assertIn("다시 시도해 주세요", result["messages"][-1].content)
        self.assertNotIn("private-token", result["messages"][-1].content)

    async def test_failed_task_does_not_leak_into_next_turn(self) -> None:
        def planner(messages):
            users = [message for message in messages if isinstance(message, HumanMessage)]
            return plan("research", "writing") if len(users) == 1 else plan("writing")

        graph = await build_supervisor_graph(
            planner=RunnableLambda(planner),
            research_agent=RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("failure"))),
            writing_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="합성 답변")]}),
        )
        config = {"configurable": {"thread_id": "supervisor-after-failure"}}
        first = await graph.ainvoke({"messages": [{"role": "user", "content": "첫 질문"}]}, config)
        second = await graph.ainvoke({"messages": [{"role": "user", "content": "후속 질문"}]}, config)
        self.assertEqual(first["tasks"][0]["status"], "failed")
        self.assertEqual([task["status"] for task in second["tasks"]], ["completed"])
        self.assertNotIn("일부 정보 수집에 실패", second["messages"][-1].content)

    async def test_planning_failure_still_propagates(self) -> None:
        graph = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("plan failure"))),
            research_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="unused")]}),
            writing_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="unused")]}),
        )
        with self.assertRaisesRegex(RuntimeError, "plan failure"):
            await graph.ainvoke(
                {"messages": [{"role": "user", "content": "합성 질문"}]},
                {"configurable": {"thread_id": "supervisor-planning-failure"}},
            )

    async def test_maximum_task_count_finishes_with_bounded_graph(self) -> None:
        graph = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: plan(*(["research"] * 5), "writing")),
            research_agent=RunnableLambda(
                lambda _: {"messages": [AIMessage(content="합성 조회 결과")]}
            ),
            writing_agent=RunnableLambda(
                lambda _: {"messages": [AIMessage(content="합성 최종 답변")]}
            ),
        )
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "최대 작업 수 질문"}]},
            {"configurable": {"thread_id": "supervisor-max-tasks"}},
        )
        self.assertEqual(result["current_task_index"], 6)
        self.assertTrue(all(task["status"] == "completed" for task in result["tasks"]))

    async def test_research_receives_only_read_only_tools(self) -> None:
        @tool
        def get_monitoring_status() -> str:
            """합성 상태 조회."""
            return "정상"

        @tool
        def search_operations_manual(query: str) -> str:
            """합성 매뉴얼 조회."""
            return query

        @tool
        def search_jira_tickets(query: str) -> str:
            """합성 이력 조회."""
            return query

        @tool
        def create_jira_ticket(summary: str) -> str:
            """합성 티켓 생성."""
            return summary

        tools = [get_monitoring_status, search_operations_manual,
                 search_jira_tickets, create_jira_ticket]
        fake_agent = RunnableLambda(lambda _: {"messages": [AIMessage(content="답변")]})
        with patch("backend.agent.supervisor_graph.create_agent", return_value=fake_agent) as create:
            await build_supervisor_graph(
                planner=RunnableLambda(lambda _: plan("writing")),
                model=FakeListChatModel(responses=["unused"]),
                tools=tools,
            )
        self.assertEqual(create.call_count, 2)
        self.assertEqual(
            {item.name for item in create.call_args_list[0].kwargs["tools"]},
            {"get_monitoring_status", "search_operations_manual", "search_jira_tickets"},
        )
        self.assertEqual(create.call_args_list[1].kwargs["tools"], [])


if __name__ == "__main__":
    unittest.main()
