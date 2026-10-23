"""HTTP 계약 테스트용 연결 없는 checkpointer context."""

from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import MemorySaver


@asynccontextmanager
async def fake_checkpointer():
    yield MemorySaver()
