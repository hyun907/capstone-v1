"""PostgreSQL checkpointer 연결·정리 경계를 외부 DB 없이 확인합니다."""

import unittest
from unittest.mock import AsyncMock, patch

from backend.persistence.checkpointer import create_checkpointer, get_database_url


class CheckpointerTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_database_url_fails_without_connection(self) -> None:
        with patch.dict("os.environ", {"DATABASE_URL": ""}):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                get_database_url()

    async def test_setup_and_connection_cleanup(self) -> None:
        saver = AsyncMock()
        manager = AsyncMock()
        manager.__aenter__.return_value = saver
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://example"}):
            with patch(
                "backend.persistence.checkpointer.AsyncPostgresSaver.from_conn_string",
                return_value=manager,
            ) as factory:
                async with create_checkpointer() as actual:
                    self.assertIs(actual, saver)
                    saver.setup.assert_awaited_once()

        factory.assert_called_once_with("postgresql://example")
        manager.__aexit__.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
