"""외부 모델 없이 LangGraph 이벤트와 SSE HTTP 계약을 검증합니다."""

import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from backend.agent.graph import build_agent
from backend.main import app
from backend.schemas.stream import TokenEvent
from backend.streaming.event_converter import convert_langgraph_events
from backend.streaming.sse_formatter import format_sse
from test_backend_agent_graph import SYNTHETIC_TOOLS, SyntheticChatModel


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


class EventConverterTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_start_end_tokens_and_done_in_order(self) -> None:
        async def graph_stream():
            yield "messages", (AIMessageChunk(content="첫 "), {})
            yield "updates", {
                "model": {
                    "messages": [AIMessage(content="", tool_calls=[{
                        "id": "call-1",
                        "name": "get_monitoring_status",
                        "args": {"system_name": "sample"},
                    }])]
                }
            }
            yield "updates", {
                "tools": {
                    "messages": [ToolMessage(
                        content="a" * 250,
                        tool_call_id="call-1",
                    )]
                }
            }
            yield "messages", (AIMessageChunk(content="답변"), {})

        events = [
            event async for event in convert_langgraph_events(graph_stream(), "thread-1")
        ]
        self.assertEqual(
            [event.type for event in events],
            ["token", "tool_call_start", "tool_call_end", "token", "done"],
        )
        self.assertEqual(events[0].content, "첫 ")
        self.assertEqual(events[1].args, {"system_name": "sample"})
        self.assertEqual(events[2].tool_name, "get_monitoring_status")
        self.assertEqual(len(events[2].result), 200)
        self.assertEqual(events[-1].thread_id, "thread-1")

    async def test_failure_does_not_emit_done(self) -> None:
        async def graph_stream():
            yield "messages", (AIMessageChunk(content="시작"), {})
            raise RuntimeError("synthetic failure")

        stream = convert_langgraph_events(graph_stream(), "thread-1")
        self.assertEqual((await anext(stream)).type, "token")
        with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            await anext(stream)

    def test_formatter_uses_sse_boundary(self) -> None:
        self.assertEqual(
            format_sse(TokenEvent(content="안녕")),
            'event: token\ndata: {"type":"token","content":"안녕"}\n\n',
        )


class StreamingEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_tool_progress_and_reuses_thread(self) -> None:
        agent = await build_agent(model=SyntheticChatModel(), tools=SYNTHETIC_TOOLS)
        with patch("backend.main.build_agent", new=AsyncMock(return_value=agent)):
            with TestClient(app) as client:
                first = client.post(
                    "/chat/stream", json={"message": "상태 확인", "thread_id": "stream-a"}
                )
                self.assertEqual(first.status_code, 200)
                self.assertTrue(first.headers["content-type"].startswith("text/event-stream"))
                events = parse_events(first.text)
                self.assertEqual(
                    [event["type"] for event in events],
                    ["tool_call_start", "tool_call_end", "token", "done"],
                )
                self.assertEqual(events[0]["tool_name"], "get_monitoring_status")
                self.assertEqual(events[1]["tool_name"], "get_monitoring_status")
                self.assertEqual(events[-1]["thread_id"], "stream-a")

                follow_up = client.post(
                    "/chat/stream", json={"message": "후속 질문", "thread_id": "stream-a"}
                )
                follow_up_events = parse_events(follow_up.text)
                self.assertIn("첫 질문: 상태 확인", follow_up_events[0]["content"])
                self.assertEqual(follow_up_events[-1]["thread_id"], "stream-a")

                invalid = client.post("/chat/stream", json={"message": ""})
                self.assertEqual(invalid.status_code, 422)
