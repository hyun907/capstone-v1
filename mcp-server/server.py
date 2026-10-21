"""ICT 운영 지원 실습용 MCP 서버."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP
from pydantic import ValidationError

from schemas import JiraTicket, JiraTicketCreated, ManualSnippet, SystemStatus

mcp = FastMCP(name="ict-operations-support")

DATA_DIR = Path(__file__).parent / "data"


@mcp.tool()
def search_operations_manual(query: str, top_k: int = 3) -> list[ManualSnippet]:
    """로컬 실습용 runbook을 키워드 등장 횟수로 검색하는 mock 도구입니다.

    공백으로 나눈 두 글자 이상 키워드를 사용하고, 점수 내림차순으로 최대 top_k건을
    반환합니다. top_k는 1~20이며, 일치 항목이나 데이터 디렉터리가 없으면 빈 목록입니다.
    """
    if not query.strip():
        raise ValueError("검색어를 입력하세요.")
    if not 1 <= top_k <= 20:
        raise ValueError("top_k는 1 이상 20 이하로 입력하세요.")

    return _mock_manual_search(query, top_k)


def _mock_manual_search(query: str, top_k: int) -> list[ManualSnippet]:
    """로컬 runbook 본문을 순회하는 실습용 키워드 검색기."""
    runbook_dir = DATA_DIR / "runbooks"
    if not runbook_dir.exists():
        return []

    data_root = DATA_DIR.resolve()
    runbook_root = runbook_dir.resolve()
    if not runbook_root.is_relative_to(data_root):
        raise RuntimeError("운영 매뉴얼 디렉터리 경로가 올바르지 않습니다.")

    keywords = [word.lower() for word in query.split() if len(word) > 1]
    if not keywords:
        return []

    scored: list[ManualSnippet] = []
    for path in sorted(runbook_dir.glob("*.md")):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", path.stem):
            continue
        try:
            resolved_path = path.resolve()
        except RuntimeError:
            continue
        except OSError:
            raise RuntimeError("운영 매뉴얼 파일 경로를 확인할 수 없습니다.") from None
        if not resolved_path.is_relative_to(runbook_root):
            continue
        try:
            contents = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise RuntimeError("운영 매뉴얼 파일을 읽을 수 없습니다.") from None

        lower = contents.lower()
        score = sum(lower.count(keyword) for keyword in keywords)
        if score == 0:
            continue

        first_match = min(lower.find(keyword) for keyword in keywords if keyword in lower)
        snippet = contents[max(0, first_match - 80) : first_match + 220].strip()
        scored.append(
            ManualSnippet(
                title=path.stem,
                source=f"runbook://incident-response/{path.stem}",
                snippet=snippet,
                score=float(score),
            )
        )

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


@mcp.tool()
def get_monitoring_status(system_name: str) -> SystemStatus:
    """로컬 실습용 monitoring.json에서 시스템 상태와 활성 알림을 조회합니다."""
    system_name = system_name.strip()
    if not system_name:
        raise ValueError("시스템 이름을 입력하세요.")

    try:
        contents = (DATA_DIR / "monitoring.json").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise RuntimeError("모니터링 데이터 파일을 읽을 수 없습니다.") from None

    try:
        monitoring_data = json.loads(contents)
    except json.JSONDecodeError:
        raise RuntimeError("모니터링 데이터 JSON 형식이 올바르지 않습니다.") from None

    if not isinstance(monitoring_data, dict):
        raise RuntimeError("모니터링 데이터 형식이 올바르지 않습니다.")

    checked_at = datetime.now(timezone.utc)
    if system_name not in monitoring_data:
        return SystemStatus(
            system_name=system_name,
            status="unknown",
            cpu_percent=0,
            memory_percent=0,
            last_checked=checked_at,
            alerts=[f"모니터링 데이터에 '{system_name}' 시스템이 없습니다."],
        )

    data = monitoring_data[system_name]
    try:
        return SystemStatus(
            system_name=system_name,
            status=data["status"],
            cpu_percent=data["cpu_percent"],
            memory_percent=data["memory_percent"],
            last_checked=checked_at,
            alerts=data.get("alerts", []),
        )
    except (KeyError, TypeError, ValidationError):
        raise RuntimeError("모니터링 데이터 형식이 올바르지 않습니다.") from None


@mcp.resource("runbook://incident-response/{incident_type}")
def get_incident_runbook(incident_type: str) -> str:
    """Return the Markdown runbook for an incident type."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", incident_type):
        return "# Invalid Incident Type\n\nUse a lowercase runbook name such as db-down."

    data_dir = DATA_DIR.resolve()
    runbook_dir = (DATA_DIR / "runbooks").resolve()
    if not runbook_dir.is_relative_to(data_dir):
        return "# Invalid Incident Type\n\nThe runbook directory must stay in data."

    runbook_path = (runbook_dir / f"{incident_type}.md").resolve()
    if not runbook_path.is_relative_to(runbook_dir):
        return "# Invalid Incident Type\n\nThe runbook path must stay in runbooks."
    if not runbook_path.is_file():
        return f"# Runbook Not Found\n\nNo runbook for incident type: {incident_type}"

    try:
        return runbook_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return f"# Runbook Unavailable\n\nUnable to read runbook for incident type: {incident_type}"


@mcp.tool()
def search_jira_tickets(
    query: str,
    project_key: str = "OPS",
    max_results: int = 5,
) -> list[JiraTicket]:
    """Jira 티켓을 모의 검색합니다. 현재는 JIRA 설정과 무관하게 실제 API를 호출하지 않습니다."""
    query = query.strip()
    project_key = project_key.strip().upper()
    if not query:
        raise ValueError("Jira 티켓 검색어를 입력하세요.")
    if not re.fullmatch(r"[A-Z][A-Z0-9]*", project_key):
        raise ValueError("Jira 프로젝트 키는 영문자로 시작하는 영문자와 숫자로 입력하세요.")
    if not 0 <= max_results <= 100:
        raise ValueError("최대 결과 수는 0에서 100 사이로 입력하세요.")

    updated_at = datetime.now(timezone.utc)
    samples = [
        JiraTicket(
            key=f"{project_key}-101",
            summary=f"[mock] '{query}' 관련 incident 조사",
            status="In Progress",
            priority="High",
            assignee="ops-oncall@example.com",
            updated=updated_at,
        ),
        JiraTicket(
            key=f"{project_key}-87",
            summary=f"[mock] '{query}' 과거 발생 사례",
            status="Done",
            priority="Medium",
            assignee=None,
            updated=updated_at,
        ),
    ]
    return samples[:max_results]


@mcp.tool()
def create_jira_ticket(
    summary: str,
    description: str,
    project_key: str = "OPS",
    issue_type: Literal["Bug", "Incident", "Task"] = "Incident",
    priority: Literal["Highest", "High", "Medium", "Low"] = "High",
) -> JiraTicketCreated:
    """실제 Jira에 쓰지 않고 생성 결과를 모의 반환합니다.

    JIRA_* 환경변수가 설정되어 있어도 외부 API를 호출하지 않습니다.
    """
    summary = summary.strip()
    description = description.strip()
    project_key = project_key.strip().upper()

    if not summary:
        raise ValueError("티켓 제목을 입력하세요.")
    if not description:
        raise ValueError("티켓 본문을 입력하세요.")
    if not re.fullmatch(r"[A-Z][A-Z0-9]*", project_key):
        raise ValueError("프로젝트 키는 영문자로 시작하는 영문자와 숫자만 사용할 수 있습니다.")
    if issue_type not in ("Bug", "Incident", "Task"):
        raise ValueError("지원하지 않는 이슈 유형입니다.")
    if priority not in ("Highest", "High", "Medium", "Low"):
        raise ValueError("지원하지 않는 우선순위입니다.")

    key = f"{project_key}-9999"
    return JiraTicketCreated(
        key=key,
        url=f"https://example.invalid/browse/{key}",
        summary=f"[mock] {summary}",
        status="To Do",
        created_at=datetime.now(timezone.utc),
    )
