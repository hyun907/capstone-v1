"""Pydantic 이벤트를 SSE 프레임으로 변환합니다."""

from backend.schemas.stream import StreamEvent


def format_sse(event: StreamEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
