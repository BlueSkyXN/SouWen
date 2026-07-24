"""Explicit-options HTTP execution core for trusted provider APIs."""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .errors import AuthError, RateLimitError, SourceUnavailableError, SouWenError

logger = logging.getLogger("souwen.http")

RequestRetryPolicy = Literal["default", "single_attempt"]


class HttpTransport:
    """HTTPX execution core configured only through explicit transport options."""

    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str],
        timeout: int | float,
        max_retries: int,
        proxy: str | None,
        follow_redirects: bool,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
            proxy=proxy,
            follow_redirects=follow_redirects,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30.0,
            ),
        )

    async def __aenter__(self) -> "HttpTransport":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """关闭底层 HTTP 连接"""
        await self._client.aclose()

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_policy: RequestRetryPolicy = "default",
    ) -> httpx.Response:
        """发送 GET 请求；默认重试，``single_attempt`` 只尝试一次。"""
        return await self._request(
            "GET", url, params=params, headers=headers, retry_policy=retry_policy
        )

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_policy: RequestRetryPolicy = "default",
    ) -> httpx.Response:
        """发送 POST 请求；默认重试，``single_attempt`` 只尝试一次。"""
        return await self._request(
            "POST", url, json=json, data=data, headers=headers, retry_policy=retry_policy
        )

    async def _request(
        self,
        method: str,
        url: str,
        retry_policy: RequestRetryPolicy = "default",
        **kwargs: Any,
    ) -> httpx.Response:
        """执行请求并统一处理错误。"""
        self._validate_retry_policy(retry_policy)

        start = time.monotonic()
        try:
            if retry_policy == "single_attempt":
                resp = await self._request_once(method, url, **kwargs)
            else:
                resp = await self._request_with_retry(method, url, **kwargs)
            elapsed = time.monotonic() - start
            logger.debug(
                "%s request completed: status=%d (%.2fs)",
                method,
                resp.status_code,
                elapsed,
            )
            return resp
        except httpx.TimeoutException as e:
            raise SourceUnavailableError("请求超时") from e
        except httpx.ConnectError as e:
            raise SourceUnavailableError("连接失败") from e

    @staticmethod
    def _validate_retry_policy(retry_policy: RequestRetryPolicy) -> None:
        if retry_policy not in ("default", "single_attempt"):
            raise ValueError(f"不支持的 retry_policy: {retry_policy!r}")

    async def _request_once(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """只执行一次请求，保留默认路径相同的 HTTP 状态映射。"""
        resp = await self._client.request(method, url, **kwargs)
        self._check_response(resp, url)
        return resp

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """带重试的请求"""
        return await self._request_once(method, url, **kwargs)

    @staticmethod
    def _parse_retry_after(value: str) -> float | None:
        """解析 Retry-After 头，支持秒数和 HTTP-date 两种格式"""
        try:
            return float(value)
        except ValueError:
            pass
        from email.utils import parsedate_to_datetime

        try:
            dt = parsedate_to_datetime(value)
            import time

            delay = dt.timestamp() - time.time()
            return max(0, delay)
        except Exception:
            return None

    @staticmethod
    def _check_response(resp: httpx.Response, url: str | None = None) -> None:
        """检查响应状态码；兼容旧 ``url`` 参数但不把它写入异常。"""
        del url
        if resp.status_code == 401:
            raise AuthError("鉴权失败")
        if resp.status_code == 403:
            raise AuthError("权限不足")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = HttpTransport._parse_retry_after(retry_after) if retry_after else None
            raise RateLimitError("限流触发", retry_after=wait)
        if resp.status_code == 404:
            return
        if resp.status_code >= 500:
            raise SourceUnavailableError(f"数据源服务器错误 ({resp.status_code})")
        if resp.status_code >= 400:
            raise SouWenError(f"请求失败 ({resp.status_code})")
