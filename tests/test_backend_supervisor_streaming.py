"""병렬 Sub-Agent 이벤트가 올바른 Task ID로 변환되는지 확인합니다."""

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
    async def test_parallel_research_maps_tokens_tools_and_batch_completion(
        self,
    ) -> None:
        pending = [
            task("task_1", "research", "pending"),
            task("task_2", "research", "pending"),
            task("task_3", "writing", "pending"),
        ]
        failed = {
            **task("task_2", "research", "failed"),
            "error_message": "도구 사용 중 문제가 발생했습니다.",
        }
        research_done = [
            task("task_1", "research", "completed", "조회 결과"),
            failed,
            pending[2],
        ]
        all_done = [
            *research_done[:2],
            task("task_3", "writing", "completed", "최종 답변"),
        ]
        ns1 = ("execute_research:run",)
        ns2 = ("execute_research:run", "1")
        ns3 = ("execute_writing:run",)

        async def graph_stream():
            yield (), "updates", {"planning": {"plan": "계획", "tasks": pending}}
            yield (
                (),
                "custom",
                {"kind": "task_started", "task_id": "task_1", "agent": "research"},
            )
            yield (
                (),
                "custom",
                {"kind": "task_started", "task_id": "task_2", "agent": "research"},
            )
            yield (
                ns2,
                "messages",
                (
                    AIMessageChunk(content="두 번째 조사"),
                    {"langgraph_node": "model", "supervisor_task_id": "task_2"},
                ),
            )
            yield (
                ns1,
                "messages",
                (
                    AIMessageChunk(content="첫 번째 조사"),
                    {"langgraph_node": "model", "supervisor_task_id": "task_1"},
                ),
            )
            yield (
                ns1,
                "updates",
                {
                    "model": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "id": "call-1",
                                        "name": "search_operations_manual",
                                        "args": {"query": "DB"},
                                    }
                                ],
                            )
                        ]
                    }
                },
            )
            yield (
                ns1,
                "updates",
                {
                    "tools": {
                        "messages": [
                            ToolMessage(
                                content="a" * 250,
                                tool_call_id="call-1",
                            )
                        ]
                    }
                },
            )
            yield (), "updates", {"execute_research": {"tasks": research_done}}
            yield (
                (),
                "custom",
                {"kind": "task_started", "task_id": "task_3", "agent": "writing"},
            )
            yield (
                ns3,
                "messages",
                (
                    AIMessageChunk(content="작성 중"),
                    {"langgraph_node": "model", "supervisor_task_id": "task_3"},
                ),
            )
            yield (), "updates", {"execute_writing": {"tasks": all_done}}
            yield (
                (),
                "updates",
                {"finalize": {"messages": [AIMessage(content="최종 답변")]}},
            )

        events = [
            event
            async for event in convert_supervisor_events(graph_stream(), "thread-a")
        ]
        self.assertEqual(
            [event.type for event in events],
            [
                "plan_created",
                "task_list_created",
                "task_started",
                "task_started",
                "sub_agent_token",
                "sub_agent_token",
                "sub_agent_tool_call",
                "sub_agent_tool_call",
                "task_completed",
                "task_completed",
                "task_started",
                "sub_agent_token",
                "task_completed",
                "token",
                "done",
            ],
        )
        self.assertEqual([events[4].task_id, events[5].task_id], ["task_2", "task_1"])
        self.assertEqual([events[6].task_id, events[7].task_id], ["task_1", "task_1"])
        self.assertEqual(events[6].args, {"query": "DB"})
        self.assertEqual(events[7].status, "end")
        self.assertEqual(len(events[7].result), 200)
        self.assertEqual([events[8].task_id, events[9].task_id], ["task_1", "task_2"])
        self.assertEqual(events[9].status, "failed")
        self.assertEqual(events[9].error_message, "도구 사용 중 문제가 발생했습니다.")
        self.assertEqual(events[-2].content, "최종 답변")
        self.assertEqual(events[-1].thread_id, "thread-a")
        frame = format_sse(events[6])
        self.assertEqual(json.loads(frame.splitlines()[1][6:])["task_id"], "task_1")

    async def test_no_research_still_completes_writing(self) -> None:
        pending = [task("task_1", "writing", "pending")]
        completed = [task("task_1", "writing", "completed", "답변")]

        async def graph_stream():
            yield (), "updates", {"planning": {"plan": "계획", "tasks": pending}}
            yield (), "updates", {"execute_research": {"tasks": pending}}
            yield (
                (),
                "custom",
                {"kind": "task_started", "task_id": "task_1", "agent": "writing"},
            )
            yield (), "updates", {"execute_writing": {"tasks": completed}}
            yield (), "updates", {"finalize": {"messages": [AIMessage(content="답변")]}}

        events = [
            event
            async for event in convert_supervisor_events(
                graph_stream(), "thread-no-research"
            )
        ]
        self.assertEqual(
            [event.type for event in events],
            [
                "plan_created",
                "task_list_created",
                "task_started",
                "task_completed",
                "token",
                "done",
            ],
        )

    async def test_failure_emits_error_without_done(self) -> None:
        async def broken_stream():
            yield (
                (),
                "updates",
                {
                    "planning": {
                        "plan": "계획",
                        "tasks": [task("task_1", "writing", "pending")],
                    }
                },
            )
            raise RuntimeError("private upstream detail")

        events = [
            event
            async for event in convert_supervisor_events(broken_stream(), "thread-b")
        ]
        self.assertEqual(
            [event.type for event in events],
            ["plan_created", "task_list_created", "error"],
        )
        self.assertEqual(events[-1].code, "STREAM_INTERRUPTED")
        self.assertTrue(events[-1].recoverable)
        self.assertNotIn("private upstream detail", events[-1].message)

    async def test_incomplete_graph_never_emits_done(self) -> None:
        async def incomplete_stream():
            yield (
                (),
                "updates",
                {
                    "planning": {
                        "plan": "계획",
                        "tasks": [task("task_1", "writing", "pending")],
                    }
                },
            )

        events = [
            event
            async for event in convert_supervisor_events(
                incomplete_stream(), "thread-c"
            )
        ]
        self.assertEqual(
            [event.type for event in events],
            ["plan_created", "task_list_created", "error"],
        )


if __name__ == "__main__":
    unittest.main()
