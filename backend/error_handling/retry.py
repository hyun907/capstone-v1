"""읽기 전용 MCP 도구의 timeout에만 적용하는 제한된 재시도."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from backend.error_handling.classification import classify_exception
from backend.schemas.error import ErrorLayer, ToolError

T = TypeVar("T")


async def with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    tool_name: str,
    max_retries: int = 2,
    initial_delay: float = 0.5,
) -> T:
    """기본 세 번 시도하며 timeout 사이에 0.5초, 1.5초를 기다립니다."""
    if max_retries < 0 or initial_delay < 0:
        raise ValueError("재시도 횟수와 대기 시간은 음수일 수 없습니다.")

    delay = initial_delay
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except TimeoutError as exc:
            if attempt == max_retries:
                error = classify_exception(
                    exc,
                    layer=ErrorLayer.TOOL,
                    context={"tool_name": tool_name, "attempts": str(attempt + 1)},
                )
                raise ToolError(error.model_copy(update={"code": "TOOL_TIMEOUT_AFTER_RETRY"})) from exc
            await asyncio.sleep(delay)
            delay *= 3
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(
                classify_exception(
                    exc,
                    layer=ErrorLayer.TOOL,
                    context={"tool_name": tool_name, "attempts": str(attempt + 1)},
                )
            ) from exc

    raise AssertionError("재시도 루프가 결과 없이 종료되었습니다.")
