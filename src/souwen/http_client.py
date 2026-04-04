"""统一 HTTP 客户端

基于 httpx async，提供：
- 自动重试（tenacity 指数退避）
- 统一超时
- User-Agent 管理
- 可选代理
- OAuth 2.0 Token 自动管理
- 统一错误处理
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from souwen.config import get_config
from souwen.exceptions import (
    AuthError,
    RateLimitError,
    SourceUnavailableError,
    SouWenError,
)

logger = logging.getLogger("souwen.http")

DEFAULT_USER_AGENT = "SouWen/0.3.0 (Academic & Patent Search Tool; https://github.com/souwen)"


class SouWenHttpClient:
    """统一 HTTP 客户端，所有数据源共用
    
    使用方式：
        async with SouWenHttpClient() as client:
            resp = await client.get("https://api.openalex.org/works")
    """

    def __init__(
        self,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ):
        config = get_config()
        self.base_url = base_url
        self.timeout = timeout or config.timeout
        self.max_retries = max_retries or config.max_retries

        default_headers = {"User-Agent": DEFAULT_USER_AGENT}
        if headers:
            default_headers.update(headers)

        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=default_headers,
            timeout=httpx.Timeout(self.timeout),
            proxy=config.proxy,
            follow_redirects=True,
        )

    async def __aenter__(self) -> "SouWenHttpClient":
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
    ) -> httpx.Response:
        """发送 GET 请求（自带重试）"""
        return await self._request("GET", url, params=params, headers=headers)

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """发送 POST 请求（自带重试）"""
        return await self._request("POST", url, json=json, data=data, headers=headers)

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """执行请求并统一处理错误"""
        start = time.monotonic()
        try:
            resp = await self._request_with_retry(method, url, **kwargs)
            elapsed = time.monotonic() - start
            logger.debug(
                "%s %s → %d (%.2fs)",
                method, url, resp.status_code, elapsed,
            )
            return resp
        except httpx.TimeoutException as e:
            raise SourceUnavailableError(f"请求超时: {url}") from e
        except httpx.ConnectError as e:
            raise SourceUnavailableError(f"连接失败: {url}") from e

    @retry(
        # 仅对网络层错误重试（超时、连接失败），业务错误（401/429/5xx）在 _check_response 中单独处理
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
        resp = await self._client.request(method, url, **kwargs)
        self._check_response(resp, url)
        return resp

    @staticmethod
    def _check_response(resp: httpx.Response, url: str) -> None:
        """检查响应状态码，抛出相应异常"""
        if resp.status_code == 401:
            raise AuthError(f"鉴权失败: {url}")
        if resp.status_code == 403:
            raise AuthError(f"权限不足: {url}")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else None
            raise RateLimitError(f"限流触发: {url}", retry_after=wait)
        if resp.status_code == 404:
            return  # 404 不抛异常，由调用方决定是否为正常情况（如资源确实不存在）
        if resp.status_code >= 500:
            raise SourceUnavailableError(
                f"数据源服务器错误 ({resp.status_code}): {url}"
            )
        if resp.status_code >= 400:
            raise SouWenError(f"请求失败 ({resp.status_code}): {url}")


class OAuthClient(SouWenHttpClient):
    """带 OAuth 2.0 Token 自动管理的 HTTP 客户端
    
    适用于 EPO OPS、CNIPA 等需要 OAuth 的数据源。
    Token 自动刷新，不会每次请求都重新获取。
    """

    def __init__(
        self,
        base_url: str,
        token_url: str,
        client_id: str,
        client_secret: str,
        **kwargs: Any,
    ):
        super().__init__(base_url=base_url, **kwargs)
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    async def _ensure_token(self) -> str:
        """确保有有效的 access token，过期则自动刷新
        
        提前 60 秒刷新，避免 token 在请求途中过期导致 401。
        """
        # 提前 60s 判定过期，留出网络延迟余量
        if self._access_token and time.monotonic() < self._token_expires_at - 60:
            return self._access_token

        logger.debug("正在获取 OAuth token: %s", self.token_url)
        resp = await self._client.post(
            self.token_url,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
        )
        if resp.status_code != 200:
            raise AuthError(f"OAuth token 获取失败: {resp.status_code} {resp.text}")

        token_data = resp.json()
        self._access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 1200)  # 默认 20 分钟
        self._token_expires_at = time.monotonic() + expires_in

        logger.debug("OAuth token 获取成功，有效期 %ds", expires_in)
        return self._access_token

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """带 OAuth token 的 GET 请求"""
        token = await self._ensure_token()
        auth_headers = {"Authorization": f"Bearer {token}"}
        if headers:
            auth_headers.update(headers)
        return await super().get(url, params=params, headers=auth_headers)

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """带 OAuth token 的 POST 请求"""
        token = await self._ensure_token()
        auth_headers = {"Authorization": f"Bearer {token}"}
        if headers:
            auth_headers.update(headers)
        return await super().post(url, json=json, data=data, headers=auth_headers)
