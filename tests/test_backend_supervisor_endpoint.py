"""합성 Supervisor로 HTTP SSE 순서와 thread_id 재사용을 확인합니다."""

import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from backend.agent.supervisor_graph import build_supervisor_graph
from backend.main import app


def parse_events(body: str) -> list[dict]:
    frames = [frame for frame in body.split("\n\n") if frame]
    events = []
    for frame in frames:
        lines = frame.splitlines()
        assert lines[0].startswith("event: ")
        assert lines[1].startswith("data: ")
        event = json.loads(lines[1][6:])
        assert event["type"] == lines[0][7:]
        events.append(event)
    return events


class SupervisorEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_plan_tasks_final_answer_and_reuses_thread(self) -> None:
        def planner(messages):
            users = [message for message in messages if isinstance(message, HumanMessage)]
            agents = ["research", "writing"] if len(users) == 1 else ["writing"]
            return {
                "plan": "합성 계획",
                "tasks": [
                    {"description": f"{agent} 작업", "agent": agent} for agent in agents
                ],
            }

        graph = await build_supervisor_graph(
            planner=RunnableLambda(planner),
            research_agent=RunnableLambda(
                lambda _: {"messages": [AIMessage(content="합성 조회 결과")]}
            ),
            writing_agent=RunnableLambda(
                lambda _: {"messages": [AIMessage(content="합성 최종 답변")]}
            ),
        )
        with patch("backend.main.build_agent", new=AsyncMock(return_value=object())):
            with patch("backend.main.build_supervisor_graph", new=AsyncMock(return_value=graph)):
                with TestClient(app) as client:
                    first = client.post(
                        "/chat/supervisor/stream", json={"message": "첫 질문"}
                    )
                    self.assertEqual(first.status_code, 200)
                    self.assertTrue(first.headers["content-type"].startswith("text/event-stream"))
                    events = parse_events(first.text)
                    self.assertEqual(
                        [event["type"] for event in events],
                        ["plan_created", "task_list_created", "task_started", "task_completed",
                         "task_started", "task_completed", "token", "done"],
                    )
                    thread_id = events[-1]["thread_id"]
                    UUID(thread_id)
                    self.assertEqual(events[-2]["content"], "합성 최종 답변")
                    self.assertEqual(events[2]["task_id"], "task_1")
                    self.assertEqual(events[4]["task_id"], "task_2")

                    followup = client.post(
                        "/chat/supervisor/stream",
                        json={"message": "후속 질문", "thread_id": thread_id},
                    )
                    followup_events = parse_events(followup.text)
                    self.assertEqual(followup_events[1]["tasks"][0]["agent"], "writing")
                    self.assertEqual(len(followup_events[1]["tasks"]), 1)
                    self.assertEqual(followup_events[-1]["thread_id"], thread_id)

                    invalid = client.post("/chat/supervisor/stream", json={"message": ""})
                    self.assertEqual(invalid.status_code, 422)

    async def test_agent_failure_becomes_failed_task_and_done(self) -> None:
        def fail(_):
            raise RuntimeError("private synthetic failure")

        graph = await build_supervisor_graph(
            planner=RunnableLambda(lambda _: {
                "plan": "합성 계획",
                "tasks": [{"description": "조회", "agent": "research"},
                          {"description": "작성", "agent": "writing"}],
            }),
            research_agent=RunnableLambda(fail),
            writing_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="답변")]}),
        )
        with patch("backend.main.build_agent", new=AsyncMock(return_value=object())):
            with patch("backend.main.build_supervisor_graph", new=AsyncMock(return_value=graph)):
                with TestClient(app) as client:
                    response = client.post(
                        "/chat/supervisor/stream", json={"message": "실패 질문"}
                    )
        events = parse_events(response.text)
        self.assertEqual(events[3]["status"], "failed")
        self.assertEqual(events[5]["status"], "completed")
        self.assertEqual(events[-1]["type"], "done")
        self.assertIn("일부 정보 수집에 실패", events[-2]["content"])
        self.assertNotIn("private synthetic failure", response.text)

    async def test_planning_failure_becomes_error_without_done(self) -> None:
        def fail(_):
            raise RuntimeError("private synthetic failure")

        graph = await build_supervisor_graph(
            planner=RunnableLambda(fail),
            research_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="unused")]}),
            writing_agent=RunnableLambda(lambda _: {"messages": [AIMessage(content="unused")]}),
        )
        with patch("backend.main.build_agent", new=AsyncMock(return_value=object())):
            with patch("backend.main.build_supervisor_graph", new=AsyncMock(return_value=graph)):
                with TestClient(app) as client:
                    response = client.post("/chat/supervisor/stream", json={"message": "합성 질문"})
        events = parse_events(response.text)
        self.assertEqual([event["type"] for event in events], ["error"])
        self.assertEqual(events[0]["code"], "STREAM_INTERRUPTED")
        self.assertTrue(events[0]["recoverable"])
        self.assertNotIn("private synthetic failure", response.text)

    async def test_stream_creation_failure_becomes_safe_error(self) -> None:
        class BrokenGraph:
            def astream(self, *_args, **_kwargs):
                raise RuntimeError("private synthetic failure")

        with patch("backend.main.build_agent", new=AsyncMock(return_value=object())):
            with patch("backend.main.build_supervisor_graph", new=AsyncMock(return_value=BrokenGraph())):
                with TestClient(app) as client:
                    response = client.post("/chat/supervisor/stream", json={"message": "합성 질문"})
        events = parse_events(response.text)
        self.assertEqual([event["type"] for event in events], ["error"])
        self.assertEqual(events[0]["code"], "STREAM_INTERRUPTED")
        self.assertNotIn("private synthetic failure", response.text)


if __name__ == "__main__":
    unittest.main()
