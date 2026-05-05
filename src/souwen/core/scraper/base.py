"""爬虫基类

提供所有爬虫共用的基础功能：
- TLS 指纹模拟（curl_cffi impersonate，绕过 JA3 检测）
- 浏览器级请求头（Sec-CH-UA 系列）
- 自适应限速（被 429 后指数退避）
- 随机请求间隔
- 自动重试（指数退避）
- 可选代理支持

技术方案涵盖 TLS 指纹伪装、自适应退避和浏览器头模拟。

文件用途：
    定义所有具体爬虫继承的 BaseScraper 抽象基类。
    集成 curl_cffi/httpx 双引擎、自适应退避算法、浏览器指纹伪装、
    频道级配置（代理、自定义请求头、HTTP 后端）等通用能力，
    使子类只需实现页面解析逻辑即可获得反反爬能力。

函数/类清单：
    BaseScraper（类）
        - 功能：爬虫基类，封装 HTTP 请求、限流、重试、指纹伪装
        - 关键属性：min_delay/max_delay 礼貌延迟范围，max_retries 最大重试次数
        - 关键变量：_backoff_multiplier 自适应退避系数，_fingerprint 浏览器指纹，
          _use_curl_cffi 是否启用 TLS 指纹模拟，_curl_session/_httpx_client 后端实例

    close() -> None
        - 功能：关闭底层 HTTP 客户端，释放连接资源
        - 通常通过 ``async with`` 上下文管理器自动调用

    _polite_delay() -> None
        - 功能：每次请求前等待随机时长，叠加自适应退避系数
        - 实现 "被限流时退避、恢复时逐步加速" 的礼貌爬取策略

    _fetch(url, method="GET", params=None, headers=None) -> httpx.Response
        - 功能：带礼貌延迟、自动重试和指纹伪装的请求方法
        - 输入：url 目标地址，method HTTP 方法，params 查询参数，headers 额外头
        - 输出：响应对象（httpx.Response 或 curl_cffi 兼容对象）
        - 异常：RateLimitError 持续被限流；SourceUnavailableError 网络/服务异常

    _do_request(method, url, params, headers) -> Any
        - 功能：根据后端选择执行实际的 HTTP 请求
        - 优先 curl_cffi（TLS 指纹），回退 httpx

模块依赖：
    - httpx: HTTP 客户端回退方案
    - curl_cffi: TLS 指纹模拟（可选，缺失时自动回退 httpx）
    - souwen.config: 全局配置（HTTP 后端、代理、超时、频道头）
    - souwen.core.fingerprint: 浏览器指纹生成
    - souwen.core.exceptions: RateLimitError / SourceUnavailableError
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from souwen.config import get_config
from souwen.core.exceptions import RateLimitError, SourceUnavailableError
from souwen.core.fingerprint import get_random_fingerprint

logger = logging.getLogger("souwen.core.scraper")

# 尝试导入 curl_cffi（TLS 指纹模拟）— 可选依赖，缺失时自动回退 httpx
_HAS_CURL_CFFI = False
try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession

    _HAS_CURL_CFFI = True
    logger.debug("curl_cffi 可用，启用 TLS 指纹模拟")
except ImportError:
    logger.info(
        "curl_cffi 未安装，TLS 指纹模拟已禁用，将使用 httpx 回退"
        "（如需启用，请安装 `souwen[tls]` 或 `souwen[scraper]`）"
    )


class BaseScraper:
    """所有爬虫的基类 — 强制礼貌爬取 + TLS 指纹模拟 + 自适应限速

    功能特性：
    - 优先使用 curl_cffi（Chrome TLS 指纹），回退到 httpx
    - 所有请求自带完整浏览器指纹头（Sec-CH-UA 系列）
    - 礼貌延迟：请求间随机间隔 + 被限流时指数退避
    - 自动重试：指数退避，重试间隔从 2s 增长到 120s
    - 支持代理和频道自定义请求头

    Args:
        min_delay: 请求最小间隔（秒），默认 2.0
        max_delay: 请求最大间隔（秒），默认 5.0
        max_retries: 最大重试次数，默认 3
        use_curl_cffi: 是否使用 curl_cffi（None 自动检测）

    Attributes:
        _backoff_multiplier: 自适应退避系数，被 429 时翻倍（上限 16x），成功时逐步回落 * 0.8
        _fingerprint: 浏览器指纹（User-Agent、Sec-CH-UA 系列头）
        _use_curl_cffi: 是否使用 curl_cffi
        _curl_session: curl_cffi AsyncSession（若启用）
        _httpx_client: httpx AsyncClient（若使用 httpx）

    HTTP 后端选择优先级：
        1. 显式参数 use_curl_cffi
        2. 频道配置 sources.<name>.http_backend
        3. 旧版全局配置 http_backend.<name>
        4. 全局默认 default_http_backend
        5. 自动检测（curl_cffi 可用则用，否则 httpx）
    """

    def __init__(
        self,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        max_retries: int = 3,
        use_curl_cffi: bool | None = None,
        follow_redirects: bool = True,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self._backoff_multiplier = 1.0  # 自适应退避系数，被 429 时翻倍，成功时逐步回落
        self._fingerprint = get_random_fingerprint()
        config = get_config()
        source_name = getattr(self, "ENGINE_NAME", None)

        # 解析 HTTP 后端：显式参数 > 频道配置 > 旧版配置 > 自动检测
        if use_curl_cffi is None:
            if source_name:
                backend = config.resolve_backend(source_name)
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

        # 解析代理：频道配置 > 全局代理
        proxy = config.resolve_proxy(source_name) if source_name else config.get_proxy()

        # 解析 base_url：频道配置覆盖 > 类属性 BASE_URL
        _class_base = getattr(self, "BASE_URL", "")
        self._resolved_base_url: str = (
            config.resolve_base_url(source_name, default=_class_base)
            if source_name
            else _class_base
        )

        # 频道自定义请求头（将在 _fetch 中合并）
        self._channel_headers: dict[str, str] = (
            config.resolve_headers(source_name) if source_name else {}
        )

        self._use_curl_cffi = use_curl_cffi
        self._follow_redirects = follow_redirects
        self._curl_session: Any = None
        self._httpx_client: httpx.AsyncClient | None = None

        if self._use_curl_cffi and _HAS_CURL_CFFI:
            logger.info("使用 curl_cffi (impersonate=%s)", self._fingerprint.impersonate)
            self._curl_session = CurlAsyncSession(
                impersonate=self._fingerprint.impersonate,
                proxy=proxy,
                timeout=config.timeout,
            )
        else:
            self._httpx_client = httpx.AsyncClient(
                timeout=httpx.Timeout(config.timeout),
                proxy=proxy,
                follow_redirects=follow_redirects,
            )

    async def __aenter__(self) -> "BaseScraper":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """关闭底层连接 — 释放 curl_cffi/httpx 客户端资源

        应在爬虫使用完毕后调用，或使用 async with 自动调用。
        """
        if self._curl_session is not None:
            await self._curl_session.close()
        if self._httpx_client is not None:
            await self._httpx_client.aclose()

    async def _polite_delay(self) -> None:
        """礼貌等待 — 随机间隔 + 自适应退避

        在每次请求前等待一段随机时间（在 min_delay 到 max_delay 之间）。
        当被限流（429）时，退避系数翻倍，延迟相应增加；
        成功请求时，系数逐步回落 * 0.8，恢复到正常水平。

        这样实现了 "被限流时退避、恢复时逐步加速" 的自适应策略。
        """
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
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """带重试和礼貌延迟的请求方法

        优先使用 curl_cffi（TLS 指纹模拟），回退到 httpx。
        自动携带完整浏览器指纹头。

        Args:
            url: 目标 URL
            method: HTTP 方法
            params: 查询参数
            headers: 额外请求头
            data: POST 表单数据（application/x-www-form-urlencoded）

        Returns:
            httpx.Response（或 curl_cffi 兼容的响应对象）

        Raises:
            RateLimitError: 重试耗尽仍被限流
            SourceUnavailableError: 服务不可用
        """
        # 使用浏览器指纹头 + 频道自定义头
        request_headers = dict(self._fingerprint.headers)
        if self._channel_headers:
            request_headers.update(self._channel_headers)
        if headers:
            request_headers.update(headers)

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            await self._polite_delay()

            try:
                resp = await self._do_request(method, url, params, request_headers, data=data)

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
        data: dict[str, Any] | None = None,
    ) -> Any:
        """执行实际的 HTTP 请求 — curl_cffi 或 httpx 双引擎

        优先使用 curl_cffi（TLS 指纹模拟，绕过 JA3 检测），
        回退到 httpx（标准库支持，无第三方依赖）。

        Args:
            method: HTTP 方法（GET、POST 等）
            url: 目标 URL
            params: 查询参数字典
            headers: 请求头字典（已包含浏览器指纹和频道自定义头）
            data: POST 表单数据

        Returns:
            响应对象（curl_cffi.Response 或 httpx.Response）

        Raises:
            RuntimeError：无可用 HTTP 客户端（极少见）
        """
        if self._use_curl_cffi and self._curl_session is not None:
            # curl_cffi 路径 — TLS 指纹模拟
            return await self._curl_session.request(
                method,
                url,
                params=params,
                headers=headers,
                data=data,
                allow_redirects=self._follow_redirects,
            )
        elif self._httpx_client is not None:
            # httpx 回退路径
            return await self._httpx_client.request(
                method, url, params=params, headers=headers, data=data
            )
        else:
            raise RuntimeError("无可用 HTTP 客户端")
