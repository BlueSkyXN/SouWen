"""爬虫基类

提供所有爬虫共用的基础功能：
- TLS 指纹模拟（curl_cffi impersonate，绕过 JA3 检测）
- 浏览器级请求头（Sec-CH-UA 系列）
- 自适应限速（被 429 后指数退避）
- 随机请求间隔
- 自动重试（指数退避）
- 可选代理支持

技术方案涵盖 TLS 指纹伪装、自适应退避和浏览器头模拟。
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from souwen.config import get_config
from souwen.exceptions import RateLimitError, SourceUnavailableError
from souwen.fingerprint import get_random_fingerprint

logger = logging.getLogger("souwen.scraper")

# 尝试导入 curl_cffi（TLS 指纹模拟）
_HAS_CURL_CFFI = False
try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession

    _HAS_CURL_CFFI = True
    logger.debug("curl_cffi 可用，启用 TLS 指纹模拟")
except ImportError:
    logger.debug("curl_cffi 不可用，回退到 httpx（可能被 JA3 检测）")


class BaseScraper:
    """所有爬虫的基类，强制礼貌爬取 + TLS 指纹模拟

    优先使用 curl_cffi（Chrome TLS 指纹），回退到 httpx。
    所有请求自带完整浏览器指纹头（Sec-CH-UA 系列）。

    Args:
        min_delay: 请求最小间隔（秒）
        max_delay: 请求最大间隔（秒）
        max_retries: 最大重试次数
        use_curl_cffi: 是否使用 curl_cffi（默认自动检测）
    """

    def __init__(
        self,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        max_retries: int = 3,
        use_curl_cffi: bool | None = None,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self._backoff_multiplier = 1.0  # 自适应退避系数，被 429 时翻倍，成功时逐步回落
        self._fingerprint = get_random_fingerprint()
        config = get_config()

        # 根据配置决定 HTTP 后端：显式参数 > 配置文件 > 自动检测
        if use_curl_cffi is None:
            source_name = getattr(self, "ENGINE_NAME", None)
            if source_name:
                backend = config.get_http_backend(source_name)
                if backend == "curl_cffi":
                    if not _HAS_CURL_CFFI:
                        logger.warning(
                            "配置要求 %s 使用 curl_cffi 但未安装，回退到 httpx", source_name
                        )
                    use_curl_cffi = _HAS_CURL_CFFI
                elif backend == "httpx":
                    use_curl_cffi = False
                else:  # auto
                    use_curl_cffi = _HAS_CURL_CFFI
            else:
                use_curl_cffi = _HAS_CURL_CFFI

        self._use_curl_cffi = use_curl_cffi
        self._curl_session: Any = None
        self._httpx_client: httpx.AsyncClient | None = None

        if self._use_curl_cffi and _HAS_CURL_CFFI:
            logger.info("使用 curl_cffi (impersonate=%s)", self._fingerprint.impersonate)
            self._curl_session = CurlAsyncSession(
                impersonate=self._fingerprint.impersonate,
                proxy=config.get_proxy(),
                timeout=config.timeout,
            )
        else:
            self._httpx_client = httpx.AsyncClient(
                timeout=httpx.Timeout(config.timeout),
                proxy=config.get_proxy(),
                follow_redirects=True,
            )

    async def __aenter__(self) -> "BaseScraper":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """关闭底层连接"""
        if self._curl_session is not None:
            await self._curl_session.close()
        if self._httpx_client is not None:
            await self._httpx_client.aclose()

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

        优先使用 curl_cffi（TLS 指纹模拟），回退到 httpx。
        自动携带完整浏览器指纹头。

        Args:
            url: 目标 URL
            method: HTTP 方法
            params: 查询参数
            headers: 额外请求头

        Returns:
            httpx.Response（或 curl_cffi 兼容的响应对象）

        Raises:
            RateLimitError: 重试耗尽仍被限流
            SourceUnavailableError: 服务不可用
        """
        # 使用浏览器指纹头
        request_headers = dict(self._fingerprint.headers)
        if headers:
            request_headers.update(headers)

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            await self._polite_delay()

            try:
                resp = await self._do_request(method, url, params, request_headers)

                if resp.status_code == 429:
                    # 被限流：退避系数翻倍（上限 16x），大幅增加后续请求间隔
                    self._backoff_multiplier = min(self._backoff_multiplier * 2, 16.0)
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        wait = float(retry_after) if retry_after else (2**attempt)
                    except (ValueError, OverflowError):
                        wait = float(2**attempt)
                    wait = min(wait, 120.0)
                    logger.warning("被限流 (429)，第 %d 次重试，等待 %.1fs", attempt, wait)
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code >= 500:
                    logger.warning("服务器错误 (%d)，第 %d 次重试", resp.status_code, attempt)
                    await asyncio.sleep(2**attempt)
                    continue

                # 请求成功：退避系数乘 0.8 逐步回落（而非直接重置为 1，避免抖动）
                self._backoff_multiplier = max(1.0, self._backoff_multiplier * 0.8)
                return resp

            except Exception as e:
                last_error = e
                logger.warning("请求失败 (%s)，第 %d 次重试", type(e).__name__, attempt)
                await asyncio.sleep(2**attempt)

        if last_error:
            raise SourceUnavailableError(
                f"重试 {self.max_retries} 次后仍失败: {url}"
            ) from last_error
        raise RateLimitError(f"重试 {self.max_retries} 次后仍被限流: {url}")

    async def _do_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> Any:
        """执行实际请求（curl_cffi 或 httpx）"""
        if self._use_curl_cffi and self._curl_session is not None:
            # curl_cffi 路径 — TLS 指纹模拟
            return await self._curl_session.request(method, url, params=params, headers=headers)
        elif self._httpx_client is not None:
            # httpx 回退路径
            return await self._httpx_client.request(method, url, params=params, headers=headers)
        else:
            raise RuntimeError("无可用 HTTP 客户端")
