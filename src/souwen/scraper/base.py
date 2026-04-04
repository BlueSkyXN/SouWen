"""爬虫基类

提供所有爬虫共用的基础功能：
- 自适应限速（被 429 后指数退避）
- 随机 User-Agent 轮换
- 随机请求间隔
- 自动重试（指数退避）
- 可选代理支持
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from souwen.config import get_config
from souwen.exceptions import RateLimitError, SourceUnavailableError

logger = logging.getLogger("souwen.scraper")

# 常用 User-Agent 池
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
]


class BaseScraper:
    """所有爬虫的基类，强制礼貌爬取

    Args:
        min_delay: 请求最小间隔（秒）
        max_delay: 请求最大间隔（秒）
        max_retries: 最大重试次数
    """

    def __init__(
        self,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        max_retries: int = 3,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self._backoff_multiplier = 1.0  # 自适应退避系数
        config = get_config()

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout),
            proxy=config.proxy,
            follow_redirects=True,
        )

    async def __aenter__(self) -> "BaseScraper":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """关闭底层 HTTP 连接"""
        await self._client.aclose()

    def _random_ua(self) -> str:
        """随机选择 User-Agent"""
        return random.choice(_USER_AGENTS)

    async def _polite_delay(self) -> None:
        """礼貌等待：随机间隔 + 自适应退避"""
        base_delay = random.uniform(self.min_delay, self.max_delay)
        actual_delay = base_delay * self._backoff_multiplier
        logger.debug("礼貌等待 %.1f 秒", actual_delay)
        await asyncio.sleep(actual_delay)

    async def _fetch(
        self,
        url: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """带重试和礼貌延迟的请求方法

        Args:
            url: 目标 URL
            method: HTTP 方法
            params: 查询参数
            headers: 额外请求头

        Returns:
            httpx.Response

        Raises:
            RateLimitError: 重试耗尽仍被限流
            SourceUnavailableError: 服务不可用
        """
        request_headers = {"User-Agent": self._random_ua()}
        if headers:
            request_headers.update(headers)

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            await self._polite_delay()

            try:
                resp = await self._client.request(
                    method, url, params=params, headers=request_headers
                )

                if resp.status_code == 429:
                    # 被限流，加大退避
                    self._backoff_multiplier = min(self._backoff_multiplier * 2, 16.0)
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else (2 ** attempt)
                    logger.warning(
                        "被限流 (429)，第 %d 次重试，等待 %.1fs", attempt, wait
                    )
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code >= 500:
                    logger.warning(
                        "服务器错误 (%d)，第 %d 次重试", resp.status_code, attempt
                    )
                    await asyncio.sleep(2 ** attempt)
                    continue

                # 成功请求，逐步恢复退避系数
                self._backoff_multiplier = max(1.0, self._backoff_multiplier * 0.8)
                return resp

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                logger.warning("请求失败 (%s)，第 %d 次重试", type(e).__name__, attempt)
                await asyncio.sleep(2 ** attempt)

        if last_error:
            raise SourceUnavailableError(f"重试 {self.max_retries} 次后仍失败: {url}") from last_error
        raise RateLimitError(f"重试 {self.max_retries} 次后仍被限流: {url}")
