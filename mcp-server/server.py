"""ICT 운영 지원 실습용 MCP 서버와 장애 대응 런북 리소스."""

import re
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP(name="ict-operations-support")

DATA_DIR = Path(__file__).parent / "data"


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
