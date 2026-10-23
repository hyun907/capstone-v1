"""외부 모델 없이 Supervisor 계획 상태와 검증 규칙을 확인합니다."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

from backend.agent.supervisor_graph import (
    MAX_PLANNING_ATTEMPTS,
    MAX_TASKS,
    build_supervisor_graph,
)


def make_plan(*agents: str) -> dict:
    return {
        "plan": "요청에 필요한 정보를 확인하고 답변을 작성합니다.",
        "tasks": [
            {"description": f"{agent} 작업 {index}", "agent": agent}
            for index, agent in enumerate(agents, start=1)
        ],
    }


class SupervisorPlanningTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_planning_and_subagents_use_separate_models(self) -> None:
        quality_model = MagicMock()
        fast_model = MagicMock()
        fast_model.with_structured_output.return_value = RunnableLambda(
            lambda _: make_plan("writing")
        )
        agent = RunnableLambda(
            lambda _: {"messages": [AIMessage(content="합성 답변")]}
        )
        tools = [
            SimpleNamespace(name=name)
            for name in (
                "get_monitoring_status",
                "search_operations_manual",
                "search_jira_tickets",
            )
        ]

        with patch("backend.agent.supervisor_graph.ChatOpenAI") as chat_model, patch(
            "backend.agent.supervisor_graph.create_agent", return_value=agent
        ) as create:
            chat_model.side_effect = [quality_model, fast_model]
            await build_supervisor_graph(tools=tools)

        self.assertEqual(
            chat_model.call_args_list,
            [
                call(model="gpt-4o", temperature=0, max_retries=1),
                call(model="gpt-4o-mini", temperature=0, max_retries=1),
            ],
        )
        fast_model.with_structured_output.assert_called_once()
        self.assertIs(create.call_args_list[0].kwargs["model"], quality_model)
        self.assertIs(create.call_args_list[1].kwargs["model"], quality_model)

    @staticmethod
    def make_agents() -> dict:
        return {
            "research_agent": RunnableLambda(
                lambda _: {"messages": [AIMessage(content="합성 조회 결과")]}
            ),
            "writing_agent": RunnableLambda(
                lambda _: {"messages": [AIMessage(content="합성 최종 답변")]}
            ),
        }

    async def test_planning_creates_pending_tasks_and_resets_next_turn(self) -> None:
        def plan_from_history(messages):
            user_messages = [message for message in messages if isinstance(message, HumanMessage)]
            return make_plan("research", "writing") if len(user_messages) == 1 else make_plan("writing")

        graph = await build_supervisor_graph(
            planner=RunnableLambda(plan_from_history), **self.make_agents()
        )
        config = {"configurable": {"thread_id": "supervisor-planning-test"}}

        planning_update = None
        async for update in graph.astream(
            {"messages": [{"role": "user", "content": "첫 질문"}]},
            config,
            stream_mode="updates",
        ):
            if "planning" in update:
                planning_update = update["planning"]
        first = await graph.aget_state(config)
        first = first.values
        self.assertEqual(first["plan"], "요청에 필요한 정보를 확인하고 답변을 작성합니다.")
        self.assertEqual([task["id"] for task in first["tasks"]], ["task_1", "task_2"])
        self.assertEqual([task["agent"] for task in first["tasks"]], ["research", "writing"])
        self.assertTrue(all(task["status"] == "pending" for task in planning_update["tasks"]))
        self.assertTrue(all(task["result"] is None for task in planning_update["tasks"]))
        self.assertEqual(planning_update["current_task_index"], 0)
        self.assertEqual(first["current_task_index"], 2)

        second = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "후속 질문"}]}, config
        )
        self.assertEqual([task["id"] for task in second["tasks"]], ["task_1"])
        self.assertEqual(second["tasks"][0]["agent"], "writing")
        self.assertEqual(second["current_task_index"], 1)
        self.assertEqual(
            [message.content for message in second["messages"] if isinstance(message, HumanMessage)],
            ["첫 질문", "후속 질문"],
        )

        separate = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "새 대화"}]},
            {"configurable": {"thread_id": "other-thread"}},
        )
        self.assertEqual(len(separate["tasks"]), 2)
        self.assertEqual(len(separate["messages"]), 2)

    async def test_invalid_plans_never_become_graph_state(self) -> None:
        invalid_cases = {
            "empty tasks": make_plan(),
            "unknown agent": make_plan("review", "writing"),
            "missing writing": make_plan("research"),
            "writing before research": make_plan("writing", "research"),
            "too many tasks": make_plan(*(["research"] * MAX_TASKS), "writing"),
            "blank description": {
                "plan": "계획",
                "tasks": [{"description": "  ", "agent": "writing"}],
            },
        }
        for name, response in invalid_cases.items():
            with self.subTest(name=name):
                graph = await build_supervisor_graph(
                    planner=RunnableLambda(lambda _: response), **self.make_agents()
                )
                with self.assertRaises(ValidationError):
                    await graph.ainvoke(
                        {"messages": [{"role": "user", "content": "질문"}]},
                        {"configurable": {"thread_id": name}},
                    )

    async def test_invalid_plan_retries_once_then_uses_valid_plan(self) -> None:
        calls = []

        def planner(messages):
            calls.append(messages)
            return make_plan("writing", "research") if len(calls) == 1 else make_plan("research", "writing")

        graph = await build_supervisor_graph(
            planner=RunnableLambda(planner), **self.make_agents()
        )
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "장애 대응 절차"}]},
            {"configurable": {"thread_id": "planner-retry"}},
        )

        self.assertEqual(len(calls), MAX_PLANNING_ATTEMPTS)
        self.assertIn("writing 작업을 정확히 하나", calls[1][-1].content)
        self.assertEqual([task["agent"] for task in result["tasks"]], ["research", "writing"])

    async def test_planning_requires_a_new_user_message(self) -> None:
        graph = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: make_plan("writing")), **self.make_agents()
        )
        with self.assertRaisesRegex(ValueError, "사용자 질문"):
            await graph.ainvoke(
                {"messages": [{"role": "assistant", "content": "기존 답변"}]},
                {"configurable": {"thread_id": "no-user-message"}},
            )
