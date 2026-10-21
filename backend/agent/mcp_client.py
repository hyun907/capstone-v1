"""로컬 MCP 서버를 stdio subprocess로 연결합니다."""

import os
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

MCP_SERVER_NAME = "ict-operations-support"
MCP_SERVER_PATH = Path(__file__).resolve().parents[2] / "mcp-server" / "server.py"
MCP_SERVER_ENV_KEYS = (
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "FASTEMBED_CACHE_PATH",
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
