"""외부 모델 없이 Supervisor 계획 상태와 검증 규칙을 확인합니다."""

import unittest

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

from backend.agent.supervisor_graph import MAX_TASKS, build_supervisor_graph


def make_plan(*agents: str) -> dict:
    return {
        "plan": "요청에 필요한 정보를 확인하고 답변을 작성합니다.",
        "tasks": [
            {"description": f"{agent} 작업 {index}", "agent": agent}
            for index, agent in enumerate(agents, start=1)
        ],
    }


class SupervisorPlanningTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_planning_requires_a_new_user_message(self) -> None:
        graph = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: make_plan("writing")), **self.make_agents()
        )
        with self.assertRaisesRegex(ValueError, "사용자 질문"):
            await graph.ainvoke(
                {"messages": [{"role": "assistant", "content": "기존 답변"}]},
                {"configurable": {"thread_id": "no-user-message"}},
            )
