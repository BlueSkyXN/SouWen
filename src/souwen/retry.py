"""统一重试策略

基于 tenacity 的分级重试装饰器：
- http_retry: 网络请求（3 次，指数退避 2-10s）
- scraper_retry: 反爬场景（5 次，指数退避 5-30s）
- poll_retry: 轮询场景（固定间隔）
"""

from __future__ import annotations

import asyncio
import logging
from functools import wraps
from typing import Any, Callable, TypeVar

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from souwen.exceptions import RateLimitError, SourceUnavailableError

logger = logging.getLogger("souwen.retry")

F = TypeVar("F", bound=Callable[..., Any])


# === Level 1: 普通网络请求重试（3 次） ===
http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(
        (
            httpx.TimeoutException,
            httpx.ConnectError,
            SourceUnavailableError,
        )
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# === Level 2: 反爬/限流场景重试（5 次，更长退避） ===
# 包含 RuntimeError 是因为 curl_cffi 在连接异常时会抛出 RuntimeError
scraper_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=5, max=30),
    retry=retry_if_exception_type(
        (
            RateLimitError,
            httpx.TimeoutException,
            httpx.ConnectError,
            RuntimeError,
            TimeoutError,
        )
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# === Level 3: CAPTCHA 识别重试（5 次，更激进退避） ===
captcha_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=5, max=30),
    retry=retry_if_exception_type((RuntimeError, TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


def poll_retry(
    max_attempts: int = 18,
    interval: float = 5.0,
    timeout_message: str = "轮询超时",
) -> Callable[[F], F]:
    """轮询重试装饰器

    以固定间隔重复调用函数，直到返回非 None/非 False 结果。
    适用于异步任务完成状态检查等场景。

    Args:
        max_attempts: 最大尝试次数
        interval: 每次尝试间隔（秒）
        timeout_message: 超时错误信息
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_attempts):
                result = await func(*args, **kwargs)
                if result:
                    return result
                if attempt < max_attempts - 1:
                    logger.debug(
                        "轮询第 %d/%d 次未获得结果，%0.1fs 后重试",
                        attempt + 1,
                        max_attempts,
                        interval,
                    )
                    await asyncio.sleep(interval)
            total = max_attempts * interval
            raise TimeoutError(f"{timeout_message} ({total:.0f}s)")

        return wrapper  # type: ignore[return-value]

    return decorator
