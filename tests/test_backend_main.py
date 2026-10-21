"""실제 모델 호출 없이 Backend HTTP 계약을 검증합니다."""

import unittest
from collections import defaultdict
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from backend.main import app


class SyntheticAgent:
    def __init__(self) -> None:
        self.histories: dict[str, list[BaseMessage]] = defaultdict(list)
        self.thread_ids: list[str] = []

    async def ainvoke(self, values: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        self.thread_ids.append(thread_id)
        question = values["messages"][0]["content"]
        history = self.histories[thread_id]
        history.append(HumanMessage(content=question))

        if question == "상태 확인":
            name = "get_monitoring_status"
            args = {"system_name": "synthetic-service"}
        elif question == "매뉴얼 확인":
            name = "search_operations_manual"
            args = {"query": "synthetic runbook"}
        else:
            name = None
            args = {}

        if name:
            call_id = f"synthetic-{len(self.thread_ids)}"
            history.extend(
                [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": name, "args": args, "id": call_id}],
                    ),
                    ToolMessage(content="synthetic result", tool_call_id=call_id),
                ]
            )
        history.append(AIMessage(content=f"합성 답변: {question}"))
        return {"messages": list(history)}


class BackendMainTests(unittest.TestCase):
    def test_health_new_and_reused_thread_only_returns_current_calls(self) -> None:
        agent = SyntheticAgent()
        with patch("backend.main.build_agent", new=AsyncMock(return_value=agent)) as builder:
            with TestClient(app) as client:
                self.assertEqual(client.get("/health").json(), {"status": "ok"})

                first = client.post("/chat", json={"message": "상태 확인"})
                self.assertEqual(first.status_code, 200)
                first_body = first.json()
                UUID(first_body["thread_id"])
                self.assertEqual(first_body["message"], "합성 답변: 상태 확인")
                self.assertEqual(
                    first_body["tool_calls"],
                    [{"name": "get_monitoring_status", "args": {"system_name": "synthetic-service"}}],
                )

                second = client.post(
                    "/chat",
                    json={"message": "매뉴얼 확인", "thread_id": first_body["thread_id"]},
                )
                self.assertEqual(second.status_code, 200)
                self.assertEqual(second.json()["thread_id"], first_body["thread_id"])
                self.assertEqual(
                    second.json()["tool_calls"],
                    [{"name": "search_operations_manual", "args": {"query": "synthetic runbook"}}],
                )

                third = client.post(
                    "/chat", json={"message": "후속 질문", "thread_id": first_body["thread_id"]}
                )
                self.assertEqual(third.status_code, 200)
                self.assertEqual(third.json()["tool_calls"], [])
                self.assertEqual(agent.thread_ids, [first_body["thread_id"]] * 3)

                other = client.post("/chat", json={"message": "별도 질문", "thread_id": "other"})
                self.assertEqual(other.status_code, 200)
                self.assertEqual(other.json()["thread_id"], "other")
                self.assertEqual(len(agent.histories["other"]), 2)

            builder.assert_awaited_once_with()

    def test_request_validation_and_agent_failure(self) -> None:
        agent = SyntheticAgent()
        agent.ainvoke = AsyncMock(side_effect=RuntimeError("synthetic-sensitive-internal-detail"))
        with patch("backend.main.build_agent", new=AsyncMock(return_value=agent)):
            with TestClient(app, raise_server_exceptions=False) as client:
                self.assertEqual(client.post("/chat", json={"message": " "}).status_code, 422)
                self.assertEqual(
                    client.post("/chat", json={"message": "질문", "thread_id": " "}).status_code,
                    422,
                )
                response = client.post("/chat", json={"message": "실패 테스트"})
                self.assertEqual(response.status_code, 500)
                self.assertNotIn("synthetic-sensitive-internal-detail", response.text)
                agent.ainvoke.assert_awaited_once()

    def test_agent_startup_failure_propagates(self) -> None:
        with patch(
            "backend.main.build_agent",
            new=AsyncMock(side_effect=RuntimeError("synthetic-startup-failure")),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic-startup-failure"):
                with TestClient(app):
                    pass


if __name__ == "__main__":
    unittest.main()
