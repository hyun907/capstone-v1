"""Jira Cloud 검색 응답을 MCP 검색 도구의 데이터 계약으로 변환합니다."""

import re
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from schemas import JiraTicket


def _jira_site_url(base_url: str) -> str:
    """API 토큰을 전송할 수 있는 Jira Cloud 사이트 주소만 허용합니다."""
    try:
        parts = urlsplit(base_url.strip())
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise ValueError("Jira 사이트 주소 형식이 올바르지 않습니다.") from None

    if (
        parts.scheme != "https"
        or host is None
        or re.fullmatch(r"[a-z0-9][a-z0-9-]*\.atlassian\.net", host) is None
        or port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Jira 사이트 주소는 https://<사이트>.atlassian.net 형식이어야 합니다.")
    return f"https://{host}"


def _jql_search_term(query: str) -> str:
    """자유 텍스트를 JQL 문자열 리터럴 안에 가둡니다."""
    if not query or any(ord(char) < 32 or ord(char) == 127 for char in query):
        raise ValueError("Jira 검색어에 빈 값이나 제어 문자를 사용할 수 없습니다.")
    return '"' + query.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _parse_ticket(issue: object) -> JiraTicket:
    if not isinstance(issue, dict) or not isinstance(issue.get("fields"), dict):
        raise RuntimeError("Jira 검색 응답 형식이 올바르지 않습니다.")

    fields = issue["fields"]
    status = fields.get("status")
    priority = fields.get("priority")
    assignee = fields.get("assignee")
    if not isinstance(status, dict) or (
        priority is not None and not isinstance(priority, dict)
    ):
        raise RuntimeError("Jira 검색 응답 형식이 올바르지 않습니다.")
    if assignee is not None and not isinstance(assignee, dict):
        raise RuntimeError("Jira 검색 응답 형식이 올바르지 않습니다.")

    try:
        return JiraTicket(
            key=issue["key"],
            summary=fields["summary"],
            status=status["name"],
            priority=(priority or {}).get("name") or "Unknown",
            assignee=assignee.get("emailAddress") if assignee else None,
            updated=fields["updated"],
        )
    except (KeyError, TypeError, ValidationError):
        raise RuntimeError("Jira 검색 응답 형식이 올바르지 않습니다.") from None


def search_jira_cloud(
    query: str,
    project_key: str,
    max_results: int,
    base_url: str,
    email: str,
    token: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[JiraTicket]:
    """Jira Cloud 검색을 수행합니다. transport는 외부 호출 없는 검증에만 사용합니다."""
    site_url = _jira_site_url(base_url)
    if re.fullmatch(r"[A-Z][A-Z0-9]*", project_key) is None:
        raise ValueError("Jira 프로젝트 키는 영문자로 시작하는 영문자와 숫자로 입력하세요.")
    if not 1 <= max_results <= 100:
        raise ValueError("최대 결과 수는 1에서 100 사이로 입력하세요.")
    jql = f"project = {project_key} AND text ~ {_jql_search_term(query)} ORDER BY updated DESC"

    try:
        with httpx.Client(
            auth=(email, token),
            timeout=10.0,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            response = client.post(
                f"{site_url}/rest/api/3/search/jql",
                json={
                    "jql": jql,
                    "maxResults": max_results,
                    "fields": ["summary", "status", "priority", "assignee", "updated"],
                },
                headers={"Accept": "application/json"},
            )
    except httpx.TimeoutException:
        raise RuntimeError("Jira 검색 요청 시간이 초과되었습니다.") from None
    except httpx.RequestError:
        raise RuntimeError("Jira 검색 서비스에 연결할 수 없습니다.") from None

    if response.status_code != 200:
        if response.status_code == 400:
            message = "Jira가 검색 조건을 거부했습니다. 검색어를 확인하세요."
        elif response.status_code == 401:
            message = "Jira 인증에 실패했습니다. 연결 설정을 확인하세요."
        elif response.status_code == 403:
            message = "Jira 티켓을 조회할 권한이 없습니다."
        elif response.status_code == 429:
            message = "Jira 요청 제한에 걸렸습니다. 잠시 후 다시 시도하세요."
        else:
            message = "Jira 검색 서비스에서 오류가 발생했습니다."
        raise RuntimeError(message)

    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError("Jira 검색 응답 JSON 형식이 올바르지 않습니다.") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("issues"), list):
        raise RuntimeError("Jira 검색 응답 형식이 올바르지 않습니다.")
    return [_parse_ticket(issue) for issue in payload["issues"][:max_results]]
