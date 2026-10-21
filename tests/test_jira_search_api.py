"""Jira 검색의 외부 응답 변환과 오프라인 분기를 검증합니다."""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp-server"))

import server
from jira_search_api import search_jira_cloud


class JiraSearchApiTests(unittest.TestCase):
    def call_cloud(self, handler, **overrides):
        options = {
            "query": "auth-service",
            "project_key": "OPS",
            "max_results": 5,
            "base_url": "https://practice.atlassian.net",
            "email": "learner@example.com",
            "token": "synthetic-token",
            "transport": httpx.MockTransport(handler),
        }
        options.update(overrides)
        return search_jira_cloud(**options)

    def test_success_and_hidden_assignee(self):
        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), "https://practice.atlassian.net/rest/api/3/search/jql")
            self.assertTrue(request.headers["Authorization"].startswith("Basic "))
            payload = json.loads(request.content)
            self.assertEqual(payload["jql"], 'project = OPS AND text ~ "auth-service" ORDER BY updated DESC')
            self.assertEqual(payload["maxResults"], 5)
            self.assertEqual(payload["fields"], ["summary", "status", "priority", "assignee", "updated"])
            return httpx.Response(200, json={"issues": [
                {"key": "OPS-10", "fields": {"summary": "Login errors", "status": {"name": "Open"}, "priority": {"name": "High"}, "assignee": {"emailAddress": "oncall@example.com"}, "updated": "2026-10-21T10:00:00.000+0000"}},
                {"key": "OPS-9", "fields": {"summary": "Older case", "status": {"name": "Done"}, "priority": None, "assignee": {"accountId": "hidden"}, "updated": "2026-10-20T10:00:00.000+0000"}},
            ], "isLast": True})

        tickets = self.call_cloud(handler)
        self.assertEqual([ticket.key for ticket in tickets], ["OPS-10", "OPS-9"])
        self.assertEqual(tickets[0].assignee, "oncall@example.com")
        self.assertIsNone(tickets[1].assignee)
        self.assertEqual(tickets[1].priority, "Unknown")
        self.assertIsNotNone(tickets[0].updated.tzinfo)

    def test_empty_and_result_cap(self):
        self.assertEqual(self.call_cloud(lambda request: httpx.Response(200, json={"issues": []})), [])
        issue = {"key": "OPS-1", "fields": {"summary": "Case", "status": {"name": "Open"}, "priority": None, "assignee": None, "updated": "2026-10-21T10:00:00+00:00"}}
        tickets = self.call_cloud(lambda request: httpx.Response(200, json={"issues": [issue, issue]}), max_results=1)
        self.assertEqual(len(tickets), 1)

    def test_http_errors_are_safe(self):
        for status, expected in [(400, "검색 조건"), (401, "인증"), (403, "권한"), (429, "요청 제한"), (503, "서비스")]:
            with self.subTest(status=status):
                with self.assertRaisesRegex(RuntimeError, expected) as caught:
                    self.call_cloud(lambda request: httpx.Response(status, text="synthetic-token private details"))
                self.assertNotIn("synthetic-token", str(caught.exception))

    def test_timeout_and_connection_error_are_safe(self):
        for error, expected in [(httpx.ReadTimeout("synthetic-token"), "시간이 초과"), (httpx.ConnectError("synthetic-token"), "연결할 수")]:
            with self.subTest(error=type(error).__name__):
                def handler(request):
                    raise error

                with self.assertRaisesRegex(RuntimeError, expected) as caught:
                    self.call_cloud(handler)
                self.assertNotIn("synthetic-token", str(caught.exception))

    def test_invalid_site_and_jql_input_never_reach_transport(self):
        def no_request(request):
            raise AssertionError("network request was attempted")

        invalid_sites = (
            "http://practice.atlassian.net",
            "https://practice.atlassian.net.evil.invalid",
            "https://user:password@practice.atlassian.net",
            "https://practice.atlassian.net/path",
            "https://practice.atlassian.net?test=1",
            "https://practice.atlassian.net:444",
        )
        for site in invalid_sites:
            with self.subTest(site=site), self.assertRaises(ValueError):
                self.call_cloud(no_request, base_url=site)
        for query, project_key in (("line\nbreak", "OPS"), ("auth", "OPS OR project=OTHER")):
            with self.subTest(query=query, project_key=project_key), self.assertRaises(ValueError):
                self.call_cloud(no_request, query=query, project_key=project_key)

        def check_escaped(request):
            jql = json.loads(request.content)["jql"]
            self.assertEqual(jql, 'project = OPS AND text ~ "x\\" OR project = OTHER" ORDER BY updated DESC')
            return httpx.Response(200, json={"issues": []})

        self.assertEqual(self.call_cloud(check_escaped, query='x" OR project = OTHER'), [])

        def check_backslash(request):
            jql = json.loads(request.content)["jql"]
            self.assertEqual(jql, 'project = OPS AND text ~ "path\\\\name" ORDER BY updated DESC')
            return httpx.Response(200, json={"issues": []})

        self.assertEqual(self.call_cloud(check_backslash, query='path\\name'), [])

    def test_redirect_is_not_followed(self):
        seen = []

        def handler(request):
            seen.append(request.url)
            return httpx.Response(302, headers={"Location": "https://other.invalid/"})

        with self.assertRaisesRegex(RuntimeError, "Jira 검색 서비스에서 오류"):
            self.call_cloud(handler)
        self.assertEqual(len(seen), 1)

    def test_invalid_response_is_not_returned_as_empty_success(self):
        for response in (httpx.Response(200, text="bad JSON"), httpx.Response(200, json={"unexpected": []}), httpx.Response(200, json={"issues": [{}]})):
            with self.subTest(response=response.text), self.assertRaises(RuntimeError):
                self.call_cloud(lambda request: response)

    def test_tool_uses_mock_for_missing_config_and_short_circuits_zero(self):
        with patch.dict(os.environ, {"JIRA_BASE_URL": "https://practice.atlassian.net"}, clear=True):
            with patch.object(server, "search_jira_cloud", side_effect=AssertionError("API called")):
                tickets = server.search_jira_tickets("auth-service")
                self.assertEqual(len(tickets), 2)
                self.assertTrue(tickets[0].summary.startswith("[mock]"))

        config = {"JIRA_BASE_URL": "https://practice.atlassian.net", "JIRA_EMAIL": "learner@example.com", "JIRA_API_TOKEN": "synthetic-token"}
        with patch.dict(os.environ, config, clear=True):
            with patch.object(server, "search_jira_cloud", side_effect=AssertionError("API called")):
                self.assertEqual(server.search_jira_tickets("auth-service", max_results=0), [])
            with patch.object(server, "search_jira_cloud", return_value=[]) as cloud:
                self.assertEqual(server.search_jira_tickets("auth-service"), [])
                cloud.assert_called_once_with("auth-service", "OPS", 5, config["JIRA_BASE_URL"], config["JIRA_EMAIL"], config["JIRA_API_TOKEN"])


if __name__ == "__main__":
    unittest.main()
