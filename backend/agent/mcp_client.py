"""로컬 MCP 서버를 stdio subprocess로 연결합니다."""

import os
import sys
from functools import wraps
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool, StructuredTool

from backend.error_handling.retry import with_retry

MCP_SERVER_NAME = "ict-operations-support"
MCP_SERVER_PATH = Path(__file__).resolve().parents[2] / "mcp-server" / "server.py"
MCP_SERVER_ENV_KEYS = (
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "FASTEMBED_CACHE_PATH",
)
READ_ONLY_MCP_TOOL_NAMES = frozenset(
    {"get_monitoring_status", "search_operations_manual", "search_jira_tickets"}
)


def create_mcp_client(server_path: Path | None = None) -> MultiServerMCPClient:
    """현재 Python으로 로컬 MCP 서버를 실행하는 클라이언트를 구성합니다.

    연결과 Tool 탐색은 ``await client.get_tools()`` 호출 시 시작됩니다.
    서버 실행 오류는 호출자에게 전파됩니다.
    """
    target = (server_path or MCP_SERVER_PATH).resolve()
    server_env = {
        key: value
        for key in MCP_SERVER_ENV_KEYS
        if (value := os.getenv(key)) is not None
    }
    return MultiServerMCPClient(
        {
            MCP_SERVER_NAME: {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(target)],
                "env": server_env,
            }
        }
    )


def wrap_mcp_tool(tool: BaseTool) -> BaseTool:
    """조회 도구 실행 실패를 ToolError로 전달합니다.

    생성 도구는 timeout 후 재호출하면 중복 쓰기가 생길 수 있어 감싸지 않습니다.
    """
    if tool.name not in READ_ONLY_MCP_TOOL_NAMES:
        return tool
    if not isinstance(tool, StructuredTool) or tool.coroutine is None:
        raise TypeError(f"조회 도구 {tool.name}의 비동기 실행 함수를 찾지 못했습니다.")

    original_coroutine = tool.coroutine

    @wraps(original_coroutine)
    async def wrapped(*args, **kwargs):
        return await with_retry(
            lambda: original_coroutine(*args, **kwargs), tool_name=tool.name
        )

    tool.coroutine = wrapped
    tool.handle_tool_error = False
    return tool


async def get_mcp_tools(client: MultiServerMCPClient | None = None) -> list[BaseTool]:
    """도구 발견 실패는 시작 단계로 전파하고, 실행 경계만 표준화합니다."""
    discovered = await (client or create_mcp_client()).get_tools()
    return [wrap_mcp_tool(tool) for tool in discovered]
