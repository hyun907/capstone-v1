"""외부 API 없이 Agent의 도구 범위와 세션 메모리를 검증합니다."""

import os
import unittest
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, tool
from langgraph.errors import GraphRecursionError
from pydantic import PrivateAttr

from backend.agent.graph import AGENT_RECURSION_LIMIT, SYSTEM_PROMPT, build_agent


@tool
def get_monitoring_status(system_name: str) -> str:
    """합성 시스템의 상태를 반환합니다."""
    return f"{system_name}: synthetic healthy"


@tool
def search_operations_manual(query: str) -> str:
    """합성 매뉴얼을 검색합니다."""
    return f"synthetic manual for {query}"


@tool
def search_jira_tickets(query: str) -> str:
    """합성 티켓을 검색합니다."""
    return f"synthetic ticket for {query}"


@tool
def create_jira_ticket(summary: str) -> str:
    """테스트 중 호출되면 안 되는 생성 도구입니다."""
    raise AssertionError(f"Jira 생성 도구가 호출되었습니다: {summary}")


@tool("get_monitoring_status")
def failing_monitoring_status(system_name: str) -> str:
    """합성 조회 오류를 발생시킵니다."""
    raise RuntimeError("synthetic-sensitive-internal-detail")


SYNTHETIC_TOOLS: list[BaseTool] = [
    get_monitoring_status,
    search_operations_manual,
    search_jira_tickets,
    create_jira_ticket,
]


class SyntheticChatModel(BaseChatModel):
    """입력 이력을 응답에 반영하는 로컬 모델."""

    always_call_tool: bool = False
    _bound_tool_names: list[str] = PrivateAttr(default_factory=list)
    _call_count: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "synthetic-chat-model"

    @property
    def bound_tool_names(self) -> list[str]:
        return self._bound_tool_names

    def bind_tools(self, tools: Sequence[BaseTool], **kwargs: Any) -> "SyntheticChatModel":
        self._bound_tool_names = [item.name for item in tools]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._call_count += 1
        if self.always_call_tool or (
            isinstance(messages[-1], HumanMessage)
            and messages[-1].content == "상태 확인"
        ):
            response = AIMessage(
                content="",
                tool_calls=[{
                    "name": "get_monitoring_status",
                    "args": {"system_name": "synthetic-service"},
                    "id": f"synthetic-call-{self._call_count}",
                }],
            )
        elif isinstance(messages[-1], ToolMessage):
            response = AIMessage(content=f"도구 결과: {messages[-1].content}")
        else:
            human_messages = [
                message.content for message in messages if isinstance(message, HumanMessage)
            ]
            response = AIMessage(content=f"첫 질문: {human_messages[0]}; 최근 질문: {human_messages[-1]}")
        return ChatResult(generations=[ChatGeneration(message=response)])


class AgentGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_remembers_same_thread_and_isolates_other_thread(self) -> None:
        model = SyntheticChatModel()
        agent = await build_agent(model=model, tools=SYNTHETIC_TOOLS)

        first = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "첫 질문"}]},
            {"configurable": {"thread_id": "thread-a"}},
        )
        follow_up = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "후속 질문"}]},
            {"configurable": {"thread_id": "thread-a"}},
        )
        other = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "별도 질문"}]},
            {"configurable": {"thread_id": "thread-b"}},
        )

        self.assertIn("첫 질문: 첫 질문", first["messages"][-1].content)
        self.assertIn("첫 질문: 첫 질문; 최근 질문: 후속 질문", follow_up["messages"][-1].content)
        self.assertIn("첫 질문: 별도 질문; 최근 질문: 별도 질문", other["messages"][-1].content)
        self.assertEqual(len([m for m in follow_up["messages"] if isinstance(m, HumanMessage)]), 2)
        self.assertEqual(len([m for m in other["messages"] if isinstance(m, HumanMessage)]), 1)
        self.assertEqual(
            set(model.bound_tool_names),
            {"get_monitoring_status", "search_operations_manual", "search_jira_tickets"},
        )
        self.assertNotIn("create_jira_ticket", model.bound_tool_names)

    async def test_read_only_tool_call_and_recursion_limit(self) -> None:
        model = SyntheticChatModel()
        agent = await build_agent(model=model, tools=SYNTHETIC_TOOLS)
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "상태 확인"}]},
            {"configurable": {"thread_id": "tool-thread"}},
        )
        self.assertIn("synthetic healthy", result["messages"][-1].content)
        self.assertEqual(agent.config["recursion_limit"], AGENT_RECURSION_LIMIT)

        looping_model = SyntheticChatModel(always_call_tool=True)
        looping_agent = await build_agent(model=looping_model, tools=SYNTHETIC_TOOLS, recursion_limit=4)
        with self.assertRaises(GraphRecursionError):
            await looping_agent.ainvoke(
                {"messages": [{"role": "user", "content": "상태 확인"}]},
                {"configurable": {"thread_id": "loop-thread"}},
            )

    async def test_tool_failure_is_sanitized(self) -> None:
        agent = await build_agent(
            model=SyntheticChatModel(),
            tools=[failing_monitoring_status, search_operations_manual, search_jira_tickets],
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "상태 확인"}]},
            {"configurable": {"thread_id": "failed-tool-thread"}},
        )
        self.assertIn("조회 도구 실행에 실패", result["messages"][-1].content)
        self.assertNotIn("synthetic-sensitive-internal-detail", result["messages"][-1].content)

    async def test_rejects_missing_tools_and_invalid_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "필수 조회 도구"):
            await build_agent(model=SyntheticChatModel(), tools=[get_monitoring_status])
        with self.assertRaisesRegex(ValueError, "recursion_limit"):
            await build_agent(model=SyntheticChatModel(), tools=SYNTHETIC_TOOLS, recursion_limit=1)

    async def test_default_model_uses_settings_without_network(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("backend.agent.graph.ChatOpenAI", return_value=SyntheticChatModel()) as factory:
                await build_agent(tools=SYNTHETIC_TOOLS)
                self.assertEqual(factory.call_args.kwargs["model"], "gpt-4o")

        with patch.dict(os.environ, {"OPENAI_MODEL": "synthetic-model"}, clear=True):
            with patch("backend.agent.graph.ChatOpenAI", return_value=SyntheticChatModel()) as factory:
                await build_agent(tools=SYNTHETIC_TOOLS)
                self.assertEqual(factory.call_args.kwargs["model"], "synthetic-model")

    async def test_loads_mcp_tools_when_tools_are_not_injected(self) -> None:
        get_tools = AsyncMock(return_value=SYNTHETIC_TOOLS)
        with patch("backend.agent.graph.create_mcp_client", return_value=SimpleNamespace(get_tools=get_tools)):
            model = SyntheticChatModel()
            agent = await build_agent(model=model)
            await agent.ainvoke(
                {"messages": [{"role": "user", "content": "합성 질문"}]},
                {"configurable": {"thread_id": "mcp-tool-thread"}},
            )
        get_tools.assert_awaited_once_with()
        self.assertNotIn("create_jira_ticket", model.bound_tool_names)

    def test_prompt_mentions_three_read_tools_and_creation_boundary(self) -> None:
        for tool_name in (
            "get_monitoring_status", "search_operations_manual", "search_jira_tickets"
        ):
            self.assertIn(tool_name, SYSTEM_PROMPT)
        self.assertIn("별도의 사용자 승인 절차", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
