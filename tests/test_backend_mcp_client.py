"""Backend MCP 어댑터의 실제 stdio subprocess 연결을 검증합니다."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.agent.mcp_client import MCP_SERVER_NAME, create_mcp_client


class BackendMcpClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovers_four_tools_and_calls_mock_read_tool(self) -> None:
        # 자식 프로세스에 실제 Jira 연결값이 전달되지 않도록 mock 모드로 고정합니다.
        with patch.dict(
            os.environ,
            {
                "JIRA_BASE_URL": "",
                "JIRA_EMAIL": "",
                "JIRA_API_TOKEN": "",
                "OPENAI_API_KEY": "synthetic-value-not-forwarded",
            },
        ):
            client = create_mcp_client()
            connection = client.connections[MCP_SERVER_NAME]
            self.assertEqual(connection["command"], sys.executable)
            self.assertEqual(connection["transport"], "stdio")
            self.assertTrue(Path(connection["args"][0]).is_absolute())
            self.assertEqual(Path(connection["args"][0]).name, "server.py")
            self.assertNotIn("OPENAI_API_KEY", connection["env"])

            tools = await client.get_tools()
            self.assertEqual(
                {tool.name for tool in tools},
                {
                    "search_operations_manual",
                    "get_monitoring_status",
                    "search_jira_tickets",
                    "create_jira_ticket",
                },
            )

            search = next(tool for tool in tools if tool.name == "search_jira_tickets")
            blocks = await search.ainvoke(
                {"query": "synthetic-incident", "project_key": "OPS", "max_results": 1}
            )
            result = json.loads(blocks[0]["text"])
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["key"], "OPS-101")
            self.assertIn("[mock]", result[0]["summary"])

    async def test_missing_server_file_propagates_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mcp-e1-") as directory:
            missing = Path(directory) / "missing_server.py"
            client = create_mcp_client(missing)
            self.assertEqual(client.connections[MCP_SERVER_NAME]["args"], [str(missing.resolve())])
            with self.assertRaises(Exception):
                await client.get_tools()


if __name__ == "__main__":
    unittest.main()
