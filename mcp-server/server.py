"""ICT 운영 지원 실습용 MCP 서버."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import FastMCP
from pydantic import ValidationError

from schemas import SystemStatus

mcp = FastMCP(name="ict-operations-support")

DATA_DIR = Path(__file__).parent / "data"


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
