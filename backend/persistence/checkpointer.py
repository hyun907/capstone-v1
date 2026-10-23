"""PostgreSQL 기반 LangGraph checkpointer의 연결 수명주기."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


def get_database_url() -> str:
    """환경 설정이 없으면 서버 시작 전에 명확한 오류를 반환합니다."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL 환경 변수가 필요합니다.")
    return url


@asynccontextmanager
async def create_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    """연결을 열고 테이블을 준비한 뒤 context 종료 때 연결을 닫습니다."""
    async with AsyncPostgresSaver.from_conn_string(get_database_url()) as checkpointer:
        await checkpointer.setup()
        yield checkpointer
