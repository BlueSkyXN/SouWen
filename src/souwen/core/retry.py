"""统一重试策略

文件用途：
    基于 tenacity 库实现分级重试装饰器，支持同步和异步函数。
    提供多个预设策略和工厂函数供自定义。

装饰器清单：
    http_retry（预设）
        - 功能：普通网络请求重试
        - 配置：3 次尝试, 指数退避 2-10s, 等待倍数 1
        - 重试条件：网络层错误（超时、连接失败）
        - 适用于：API 调用、网络波动场景

    scraper_retry（预设）
        - 功能：反爬/限流场景重试
        - 配置：5 次尝试, 指数退避 5-30s, 等待倍数 2
        - 重试条件：限流、超时、连接失败、RuntimeError、TimeoutError
        - 适用于：爬虫请求、被反爬拦截的场景

    captcha_retry（预设）
        - 功能：CAPTCHA 识别重试
        - 配置：5 次尝试, 指数退避 5-30s, 等待倍数 2
        - 重试条件：RuntimeError、TimeoutError
        - 适用于：CAPTCHA 识别超时场景

    poll_retry(max_attempts, interval, timeout_message)（工厂）
        - 功能：轮询重试（仅 async）
        - 入参：max_attempts 最大尝试次数, interval 固定间隔(秒),
                timeout_message 超时错误信息
        - 出参：装饰器函数
        - 行为：以固定间隔重复调用，直到返回非 None/非 False 结果
        - 异常：全部尝试失败则抛 TimeoutError

    make_retry(attempts, min_wait, max_wait, multiplier, retry_on)（工厂）
        - 功能：自定义重试装饰器构造
        - 入参：attempts 最大尝试数, min_wait/max_wait 指数退避范围,
                multiplier 倍数, retry_on 异常类型元组
        - 出参：可装饰 def/async def 的装饰器
        - 说明：retry_on 必须显式指定，避免过宽捕获

异常常量：
    DEFAULT_HTTP_EXCEPTIONS: tuple
        - 网络层错误：TimeoutException, ConnectError, SourceUnavailableError

    DEFAULT_SCRAPER_EXCEPTIONS: tuple
        - 爬虫层错误：RateLimitError, TimeoutException, ConnectError,
                   RuntimeError, TimeoutError
        - 注意：RuntimeError 因 curl_cffi 底层异常而纳入

    DEFAULT_CAPTCHA_EXCEPTIONS: tuple
        - CAPTCHA 层错误：RuntimeError, TimeoutError

兼容性说明：
    - tenacity @retry 通过 inspect.iscoroutinefunction 自动分发到同步/异步路径
    - http_retry / scraper_retry / captcha_retry 可同时装饰 def 或 async def
    - poll_retry 只支持 async def（内部使用 asyncio.sleep）

自定义重试例子：

    from souwen.retry import make_retry
    my_retry = make_retry(attempts=4, retry_on=(MyError, httpx.ReadError))

    @my_retry
    async def my_function():
        ...
"""

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

from souwen.exceptions import RateLimitError, SourceUnavailableError

logger = logging.getLogger("souwen.retry")

F = TypeVar("F", bound=Callable[..., Any])


# 默认会被重试的异常集合 —— 调用方可复用以组合自定义策略
DEFAULT_HTTP_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.TimeoutException,
    httpx.ConnectError,
    SourceUnavailableError,
)

# 反爬层默认异常集合。
# 注意：此处显式纳入 ``RuntimeError`` 是因为 curl_cffi 在底层连接
# 异常时会抛出裸 RuntimeError（而非 httpx 异常）；若将来彻底迁移出
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
