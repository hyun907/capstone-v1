"""Jira Cloud 티켓 생성 요청과 응답 처리."""

import re
from datetime import datetime, timezone

import httpx

from jira_site import jira_site_url
from schemas import JiraTicketCreated


def _create_jira_cloud(
    summary: str,
    description: str,
    project_key: str,
    issue_type: str,
    priority: str,
    base_url: str,
    email: str,
    token: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> JiraTicketCreated:
    """Jira Cloud REST API로 티켓을 생성합니다. transport는 테스트용 주입 지점입니다."""
    if not re.fullmatch(r"[A-Z][A-Z0-9]*", project_key):
        raise ValueError("Jira 프로젝트 키가 올바르지 않습니다.")
    if not email or not token:
        raise ValueError("Jira 인증 설정이 비어 있습니다.")

    root = jira_site_url(base_url)
    description_content = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}] if line else []}
        for line in description.splitlines()
    ]
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {"type": "doc", "version": 1, "content": description_content},
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
        }
    }

    try:
        with httpx.Client(
            transport=transport, timeout=15.0, follow_redirects=False, trust_env=False
        ) as client:
            response = client.post(
                f"{root}/rest/api/3/issue",
                json=payload,
                auth=(email, token),
                headers={"Accept": "application/json"},
            )
    except httpx.TimeoutException:
        raise RuntimeError(
            "Jira 티켓 생성 요청 시간이 초과되었습니다. 중복 생성을 피하려면 Jira에서 생성 여부를 확인하세요."
        ) from None
    except httpx.RequestError:
        raise RuntimeError(
            "Jira 티켓 생성 결과를 확인할 수 없습니다. 중복 생성을 피하려면 Jira에서 확인하세요."
        ) from None

    if response.status_code == 401:
        raise PermissionError("Jira 인증 정보를 확인하세요.")
    if response.status_code == 403:
        raise PermissionError("Jira 티켓 생성 권한이 없습니다.")
    if response.status_code in (400, 422):
        raise ValueError("Jira 프로젝트, 이슈 유형, 우선순위 또는 필드 값을 확인하세요.")
    if response.status_code != 201:
        raise RuntimeError(
            f"Jira 티켓 생성 결과를 확인할 수 없습니다 (HTTP {response.status_code}). Jira에서 생성 여부를 확인하세요."
        )

    try:
        data = response.json()
        key = data["key"]
    except (ValueError, TypeError, KeyError):
        raise RuntimeError("Jira 티켓 생성 응답 형식이 올바르지 않습니다. Jira에서 생성 여부를 확인하세요.") from None
    if not isinstance(key, str) or not re.fullmatch(rf"{re.escape(project_key)}-[1-9][0-9]*", key):
        raise RuntimeError("Jira 티켓 생성 응답 키가 올바르지 않습니다. Jira에서 생성 여부를 확인하세요.")

    return JiraTicketCreated(
        key=key,
        url=f"{root}/browse/{key}",
        summary=summary,
        status="Unknown",
        created_at=datetime.now(timezone.utc),
    )
