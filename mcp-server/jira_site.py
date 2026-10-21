"""Jira Cloud 사이트 주소 검증."""

import re
from urllib.parse import urlsplit


def jira_site_url(base_url: str) -> str:
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
