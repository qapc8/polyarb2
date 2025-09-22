"""Retry helpers using :mod:`tenacity`."""

from __future__ import annotations

from typing import Awaitable, Callable, TypeVar

from tenacity import AsyncRetrying, RetryError, retry_if_exception_type, stop_after_attempt, wait_exponential

T = TypeVar("T")


async def retry_async(
    func: Callable[[], Awaitable[T]],
    attempts: int = 3,
    initial: float = 0.2,
    max_wait: float = 2.0,
    retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Execute ``func`` with exponential backoff."""

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(min=initial, max=max_wait),
        retry=retry_if_exception_type(retry_exceptions),
        reraise=True,
    ):
        with attempt:
            return await func()
    raise RetryError("retry exhausted")
