"""실제 네트워크 연결 없이 Jira 티켓 생성 경로를 검증합니다."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp-server"))

import server  # noqa: E402
from jira_create_api import _create_jira_cloud  # noqa: E402
from schemas import JiraTicketCreated  # noqa: E402


class JiraCreateApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.args = (
            "로그인 오류 증가",
            "실패율 20%\n\n추가 조사 필요",
            "OPS",
            "Incident",
            "High",
            "https://team.atlassian.net",
            "test@example.invalid",
            "fake-secret-token",
        )

    def test_success_sends_adf_and_returns_created_ticket(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(201, json={"key": "OPS-123", "id": "123"})

        result = _create_jira_cloud(*self.args, transport=httpx.MockTransport(respond))

        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(str(request.url), "https://team.atlassian.net/rest/api/3/issue")
        self.assertTrue(request.headers["authorization"].startswith("Basic "))
        self.assertEqual(request.headers["accept"], "application/json")
        fields = json.loads(request.content)["fields"]
        self.assertEqual(fields["project"], {"key": "OPS"})
        self.assertEqual(fields["summary"], "로그인 오류 증가")
        self.assertEqual(fields["issuetype"], {"name": "Incident"})
        self.assertEqual(fields["priority"], {"name": "High"})
        self.assertEqual(
            fields["description"],
            {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "실패율 20%"}]},
                    {"type": "paragraph", "content": []},
                    {"type": "paragraph", "content": [{"type": "text", "text": "추가 조사 필요"}]},
                ],
            },
        )
        self.assertEqual(result.key, "OPS-123")
        self.assertEqual(result.url, "https://team.atlassian.net/browse/OPS-123")
        self.assertEqual(result.summary, "로그인 오류 증가")
        self.assertEqual(result.status, "Unknown")
        self.assertIsNotNone(result.created_at.tzinfo)

    def test_error_statuses_are_distinct_and_do_not_echo_secret_response(self) -> None:
        scenarios = [
            (401, PermissionError, "인증"),
            (403, PermissionError, "권한"),
            (400, ValueError, "필드"),
            (422, ValueError, "필드"),
            (500, RuntimeError, "HTTP 500"),
        ]
        for status, error_type, message in scenarios:
            with self.subTest(status=status):
                transport = httpx.MockTransport(
                    lambda _: httpx.Response(status, text="fake-secret-token response")
                )
                with self.assertRaises(error_type) as raised:
                    _create_jira_cloud(*self.args, transport=transport)
                self.assertIn(message, str(raised.exception))
                self.assertNotIn("fake-secret-token", str(raised.exception))

    def test_timeout_and_connection_error_report_uncertain_outcome(self) -> None:
        for error, expected in (
            (httpx.ReadTimeout("fake-secret-token"), "시간이 초과"),
            (httpx.ConnectError("fake-secret-token"), "결과를 확인할 수 없습니다"),
        ):
            with self.subTest(error=type(error).__name__):
                transport = httpx.MockTransport(lambda _: (_ for _ in ()).throw(error))
                with self.assertRaises(RuntimeError) as raised:
                    _create_jira_cloud(*self.args, transport=transport)
                self.assertIn(expected, str(raised.exception))
                self.assertIn("Jira에서", str(raised.exception))
                self.assertNotIn("fake-secret-token", str(raised.exception))

    def test_invalid_url_and_project_are_rejected_before_request(self) -> None:
        count = 0

        def respond(_: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            return httpx.Response(201, json={"key": "OPS-123"})

        transport = httpx.MockTransport(respond)
        for base_url in (
            "http://team.atlassian.net",
            "https://evil.invalid",
            "https://user:pass@team.atlassian.net",
            "https://team.atlassian.net/jira",
            "https://team.atlassian.net/?x=1",
            "https://team.atlassian.net:443",
            "https://team.atlassian.net:8443",
            "https://a.b.atlassian.net",
        ):
            with self.subTest(base_url=base_url), self.assertRaises(ValueError):
                _create_jira_cloud(*self.args[:5], base_url, *self.args[6:], transport=transport)
        with self.assertRaises(ValueError):
            _create_jira_cloud(*self.args[:2], "OPS OR 1=1", *self.args[3:], transport=transport)
        self.assertEqual(count, 0)

    def test_malformed_success_response_has_no_secret_and_warns_to_check(self) -> None:
        for response in (
            httpx.Response(201, text="fake-secret-token"),
            httpx.Response(201, json={"key": "OTHER-123"}),
        ):
            with self.subTest(response=response.text):
                with self.assertRaises(RuntimeError) as raised:
                    _create_jira_cloud(*self.args, transport=httpx.MockTransport(lambda _: response))
                self.assertIn("Jira에서 생성 여부", str(raised.exception))
                self.assertNotIn("fake-secret-token", str(raised.exception))


class JiraCreateToolTests(unittest.TestCase):
    def test_mock_when_config_missing_and_live_branch_requires_confirmation(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = server.create_jira_ticket("제목", "본문")
        self.assertEqual(result.key, "OPS-9999")
        self.assertTrue(result.summary.startswith("[mock] "))
        self.assertEqual(result.url, "https://example.invalid/browse/OPS-9999")

        with patch.dict(
            "os.environ",
            {"JIRA_BASE_URL": "https://team.atlassian.net", "JIRA_EMAIL": "fake@example.invalid"},
            clear=True,
        ):
            self.assertEqual(server.create_jira_ticket("제목", "본문").key, "OPS-9999")

        config = {
            "JIRA_BASE_URL": "https://team.atlassian.net",
            "JIRA_EMAIL": "fake@example.invalid",
            "JIRA_API_TOKEN": "fake-token",
        }
        for empty_key in config:
            with self.subTest(empty_key=empty_key), patch.dict(
                "os.environ", {**config, empty_key: "  \t "}, clear=True
            ), patch.object(server, "_create_jira_cloud") as create:
                result = server.create_jira_ticket("제목", "본문", user_confirmed=True)
                self.assertEqual(result.key, "OPS-9999")
                self.assertTrue(result.summary.startswith("[mock] "))
                create.assert_not_called()

        expected = JiraTicketCreated(
            key="OPS-123",
            url="https://team.atlassian.net/browse/OPS-123",
            summary="제목",
            status="Unknown",
            created_at="2026-01-01T00:00:00Z",
        )
        with patch.dict("os.environ", config, clear=True), patch.object(
            server, "_create_jira_cloud", return_value=expected
        ) as create:
            with self.assertRaises(PermissionError):
                server.create_jira_ticket("제목", "본문")
            create.assert_not_called()
            self.assertEqual(server.create_jira_ticket("제목", "본문", user_confirmed=True), expected)
            create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
