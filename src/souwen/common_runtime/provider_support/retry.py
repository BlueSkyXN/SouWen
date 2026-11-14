"""统一重试策略"""

from __future__ import annotations

import asyncio
import logging
from functools import wraps
from typing import Any, Callable, TypeVar

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from souwen.common_runtime.transport import RateLimitError, SourceUnavailableError

logger = logging.getLogger("souwen.common_runtime.provider_support.retry")

F = TypeVar("F", bound=Callable[..., Any])


# 默认会被重试的异常集合 —— 调用方可复用以组合自定义策略
DEFAULT_HTTP_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.TimeoutException,
    httpx.ConnectError,
    SourceUnavailableError,
)

# 反爬层默认异常集合。
# 注意：此处显式纳入 ``RuntimeError`` 是因为 curl_cffi 在底层连接
# 异常时会抛出裸 RuntimeError（而非 httpx 异常）；若将来不再使用
# curl_cffi 可从此集合移除。
DEFAULT_SCRAPER_EXCEPTIONS: tuple[type[BaseException], ...] = (
    RateLimitError,
    httpx.TimeoutException,
    httpx.ConnectError,
    RuntimeError,
    TimeoutError,
)

DEFAULT_CAPTCHA_EXCEPTIONS: tuple[type[BaseException], ...] = (
    RuntimeError,
    TimeoutError,
)


def make_retry(
    *,
    attempts: int = 3,
    min_wait: float = 2.0,
    max_wait: float = 10.0,
    multiplier: float = 1.0,
    retry_on: tuple[type[BaseException], ...] = DEFAULT_HTTP_EXCEPTIONS,
) -> Callable[[F], F]:
    """构造一个 tenacity 重试装饰器

    tenacity ``@retry`` 原生兼容同步与异步函数，返回值可同时装饰
    ``def`` 与 ``async def``。

    Args:
        attempts: 最大尝试次数（含首次）
        min_wait: 最小等待秒数（指数退避下界）
        max_wait: 最大等待秒数（指数退避上界）
        multiplier: 退避倍数（每次重试等待时间乘以此倍数）
        retry_on: 触发重试的异常类型元组；必须显式指定以避免过宽捕获

    Returns:
        装饰器，可装饰 def 或 async def 函数

    说明：
        - 指数退避计算：wait_time = min(max_wait, min_wait * multiplier^attempt)
        - 示例：min_wait=2, max_wait=10, multiplier=1 → 等待 2, 4, 8, 10, 10...
        - before_sleep 会在每次重试前记录 WARNING 级别日志
    """
    return retry(  # type: ignore[return-value]
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(retry_on),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


# === Level 1: 普通网络请求重试（3 次） ===
http_retry = make_retry(
    attempts=3,
    min_wait=2,
    max_wait=10,
    multiplier=1,
    retry_on=DEFAULT_HTTP_EXCEPTIONS,
)

# === Level 2: 反爬/限流场景重试（5 次，更长退避） ===
scraper_retry = make_retry(
    attempts=5,
    min_wait=5,
    max_wait=30,
    multiplier=2,
    retry_on=DEFAULT_SCRAPER_EXCEPTIONS,
)

# === Level 3: CAPTCHA 识别重试（5 次，激进退避） ===
captcha_retry = make_retry(
    attempts=5,
    min_wait=5,
    max_wait=30,
    multiplier=2,
    retry_on=DEFAULT_CAPTCHA_EXCEPTIONS,
)


def poll_retry(
    max_attempts: int = 18,
    interval: float = 5.0,
    timeout_message: str = "轮询超时",
) -> Callable[[F], F]:
    """轮询重试装饰器（仅 async）

    以固定间隔重复调用函数，直到返回非 None/非 False 结果。

    Args:
        max_attempts: 最大尝试次数
        interval: 每次尝试间隔（秒）
        timeout_message: 超时时的错误信息前缀

    Returns:
        装饰器（仅支持 async def）

    行为：
        1. 调用被装饰函数
        2. 如果返回真值（非 None/非 False），立即返回
        3. 否则睡眠 interval 秒后重试
        4. 达到 max_attempts 后仍未获得结果，抛 TimeoutError

    示例：

        @poll_retry(max_attempts=10, interval=3, timeout_message="查询超时")
        async def wait_for_result():
            result = await fetch_status()
            return result if result.ready else None
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
