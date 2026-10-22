"""합성 Sub-Agent로 Supervisor 작업 순서, 상태 전환, 실패를 확인합니다."""

import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from backend.agent.supervisor_graph import build_supervisor_graph


def plan(*agents: str) -> dict:
    return {
        "plan": "필요한 자료를 확인하고 답변합니다.",
        "tasks": [
            {"description": f"{agent} 작업 {index}", "agent": agent}
            for index, agent in enumerate(agents, start=1)
        ],
    }


class SupervisorExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_sequential_updates_and_writing_context(self) -> None:
        calls = []

        def research(request):
            calls.append(("research", request["messages"][-1].content))
            return {"messages": [AIMessage(content=f"조회 결과 {len(calls)}")]}

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
            ["planning", "start_task", "execute_task", "start_task", "execute_task",
             "start_task", "execute_task", "finalize"],
        )
        self.assertEqual(
            [update["start_task"]["tasks"][index]["status"]
             for index, update in enumerate(updates[1:6:2])],
            ["in_progress"] * 3,
        )
        self.assertEqual(
            [update["execute_task"]["tasks"][index]["status"]
             for index, update in enumerate(updates[2:7:2])],
            ["completed"] * 3,
        )
        self.assertEqual([name for name, _ in calls], ["research", "research", "writing"])
        self.assertIn("DB와 네트워크를 비교해 주세요", calls[-1][1])
        self.assertIn("조회 결과 1", calls[-1][1])
        self.assertIn("조회 결과 2", calls[-1][1])
        final = (await graph.aget_state(config)).values
        self.assertEqual(final["current_task_index"], 3)
        self.assertEqual(final["messages"][-1].content, "두 결과를 통합한 답변")

    async def test_followup_replans_and_empty_or_failed_agent_stops(self) -> None:
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
        with self.assertRaisesRegex(RuntimeError, "합성 도구 실패"):
            await failed.ainvoke(
                {"messages": [{"role": "user", "content": "실패 질문"}]},
                {"configurable": {"thread_id": "supervisor-failure"}},
            )

        empty = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: plan("writing")),
            research_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="조회 결과")]}),
            writing_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="   ")]}),
        )
        with self.assertRaisesRegex(ValueError, "빈 답변"):
            await empty.ainvoke(
                {"messages": [{"role": "user", "content": "빈 답변 질문"}]},
                {"configurable": {"thread_id": "supervisor-empty"}},
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
