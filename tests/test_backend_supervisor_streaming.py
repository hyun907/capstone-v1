"""합성 중첩 LangGraph 스트림의 Supervisor SSE 계약을 확인합니다."""

import json
import unittest

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from backend.streaming.event_converter import convert_supervisor_events
from backend.streaming.sse_formatter import format_sse


def task(task_id: str, agent: str, status: str, result: str | None = None) -> dict:
    return {
        "id": task_id,
        "description": f"{agent} 작업",
        "agent": agent,
        "status": status,
        "result": result,
    }


class SupervisorStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_order_task_mapping_tool_events_and_final_answer_once(self) -> None:
        pending = [task("task_1", "research", "pending"), task("task_2", "writing", "pending")]
        first_running = [task("task_1", "research", "in_progress"), pending[1]]
        first_done = [task("task_1", "research", "completed", "검색 결과"), pending[1]]
        second_running = [first_done[0], task("task_2", "writing", "in_progress")]
        both_done = [first_done[0], task("task_2", "writing", "completed", "최종 답변")]

        async def graph_stream():
            yield (), "updates", {"planning": {"plan": "계획", "tasks": pending}}
            yield (), "updates", {"start_task": {"tasks": first_running}}
            yield ("execute_task:run-1",), "messages", (
                AIMessageChunk(content="", tool_call_chunks=[{
                    "name": "search_operations_manual", "args": '{"query":"', "id": "call-1", "index": 0,
                }]),
                {"langgraph_node": "model"},
            )
            yield ("execute_task:run-1",), "updates", {"model": {"messages": [AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "search_operations_manual", "args": {"query": "DB"}}],
            )]}}
            yield ("execute_task:run-1",), "updates", {"tools": {"messages": [ToolMessage(
                content="a" * 250, tool_call_id="call-1",
            )]}}
            yield ("execute_task:run-1",), "messages", (
                AIMessageChunk(content="조사 중"), {"langgraph_node": "model"},
            )
            yield (), "updates", {"execute_task": {"tasks": first_done, "current_task_index": 1}}
            yield (), "updates", {"start_task": {"tasks": second_running}}
            yield ("execute_task:run-2",), "messages", (
                AIMessageChunk(content="작성 중"), {"langgraph_node": "model"},
            )
            yield (), "updates", {"execute_task": {"tasks": both_done, "current_task_index": 2}}
            yield (), "messages", (AIMessage(content="최종 답변"), {"langgraph_node": "finalize"})
            yield (), "updates", {"finalize": {"messages": [AIMessage(content="최종 답변")]}}

        events = [event async for event in convert_supervisor_events(graph_stream(), "thread-a")]
        self.assertEqual(
            [event.type for event in events],
            ["plan_created", "task_list_created", "task_started", "sub_agent_tool_call",
             "sub_agent_tool_call", "sub_agent_token", "task_completed", "task_started",
             "sub_agent_token", "task_completed", "token", "done"],
        )
        self.assertEqual(events[2].task_id, "task_1")
        self.assertEqual(events[3].args, {"query": "DB"})
        self.assertEqual(events[4].tool_name, "search_operations_manual")
        self.assertEqual(events[4].status, "end")
        self.assertEqual(len(events[4].result), 200)
        self.assertEqual(events[5].task_id, "task_1")
        self.assertEqual(events[8].task_id, "task_2")
        self.assertEqual(events[-2].content, "최종 답변")
        self.assertEqual(events[-1].thread_id, "thread-a")
        frame = format_sse(events[3])
        self.assertEqual(json.loads(frame.splitlines()[1][6:])["task_id"], "task_1")
        self.assertTrue(frame.endswith("\n\n"))

    async def test_failure_emits_error_without_done(self) -> None:
        async def broken_stream():
            yield (), "updates", {"planning": {"plan": "계획", "tasks": [task("task_1", "writing", "pending")]}}
            raise RuntimeError("private upstream detail")

        events = [event async for event in convert_supervisor_events(broken_stream(), "thread-b")]
        self.assertEqual([event.type for event in events], ["plan_created", "task_list_created", "error"])
        self.assertEqual(events[-1].code, "STREAM_FAILED")
        self.assertNotIn("private upstream detail", events[-1].message)

    async def test_incomplete_graph_never_emits_done(self) -> None:
        async def incomplete_stream():
            yield (), "updates", {"planning": {"plan": "계획", "tasks": [task("task_1", "writing", "pending")]}}

        events = [event async for event in convert_supervisor_events(incomplete_stream(), "thread-c")]
        self.assertEqual([event.type for event in events], ["plan_created", "task_list_created", "error"])


if __name__ == "__main__":
    unittest.main()
