"""统一 HTTP 客户端

文件用途：
    提供全局的异步 HTTP 客户端。基于 httpx，集成了自动重试、代理配置、OAuth 令牌管理、
    统一超时和错误处理。所有数据源均通过该客户端发起请求。

类清单：
    SouWenHttpClient (context manager)
        - 功能：异步 HTTP 客户端，包含重试逻辑和代理管理
        - 初始化参数：base_url, headers, timeout, max_retries, source_name
        - 主要方法：
          * get(url, **kwargs) — GET 请求（带重试）
          * post(url, **kwargs) — POST 请求（带重试）
          * get_json(url, ...) — GET 并解析 JSON
          * post_json(url, ...) — POST 并解析 JSON
          * close() — 关闭底层连接
          * _apply_oauth_token(headers) — OAuth 令牌注入
        - 特性：自动代理应用、User-Agent 管理、OAuthClient 集成

    OAuthClient (abstract)
        - 功能：OAuth 令牌管理基类（各数据源子类实现）
        - 主要方法：
          * get_access_token(scope) → str — 获取或刷新令牌（缓存化）
          * _fetch_token_impl(scope) — 子类实现的令牌获取逻辑

    _SemanticScholarOAuthClient (OAuthClient)
        - 功能：Semantic Scholar API 的 OAuth 令牌管理
        - 初始化参数：api_key
        - 特性：缓存令牌，支持多个 scope，自动过期刷新

    get_http_client(source_name) → SouWenHttpClient
        - 功能：获取或创建数据源专用的 HTTP 客户端
        - 参数：source_name (数据源名)
        - 返回：SouWenHttpClient 实例

重试策略：
    - 所有 HTTP 请求使用 tenacity 指数退避重试
    - 重试条件：HTTP 429 (Rate Limit) 和网络错误
    - 不重试：HTTP 4xx (除 429)、HTTP 5xx (用户错误)

模块依赖：
    - httpx: 异步 HTTP 库
    - tenacity: 重试装饰器
    - souwen.config: 获取全局配置（代理、超时等）
    - souwen.exceptions: 错误类型
"""

from __future__ import annotations

import asyncio
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

from souwen import __version__
from souwen.config import get_config
from souwen.exceptions import (
    AuthError,
    RateLimitError,
    SourceUnavailableError,
    SouWenError,
)

logger = logging.getLogger("souwen.http")

DEFAULT_USER_AGENT = (
    f"SouWen/{__version__} (Academic & Patent Search Tool; https://github.com/BlueSkyXN/SouWen)"
)


class SouWenHttpClient:
    """统一 HTTP 客户端（async context manager）

    所有数据源共用的 HTTP 客户端，提供以下功能：
    - 统一的重试策略（指数退避）
    - 代理配置（全局/源级别支持）
    - User-Agent 设定
    - 超时和重试次数配置
    - OAuth 令牌自动管理（集成 OAuthClient）
    - 统一错误处理和日志

    使用方式：
        async with SouWenHttpClient(source_name="semantic_scholar") as client:
            resp = await client.get("https://api.semanticscholar.org/...")

    Args:
        base_url: 基础 URL（可选，用于 relative URL）
        headers: 默认请求头（dict）
        timeout: 请求超时秒数（默认从 config 读取）
        max_retries: 最大重试次数（默认从 config 读取）
        source_name: 数据源名（用于日志和配置查询）
    """

    def __init__(
        self,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        source_name: str | None = None,
    ):
        config = get_config()

        # 频道配置可覆盖 base_url
        if source_name:
            base_url = config.resolve_base_url(source_name, default=base_url)
            proxy = config.resolve_proxy(source_name)
            channel_headers = config.resolve_headers(source_name)
        else:
            proxy = config.get_proxy()
            channel_headers = {}

        self.base_url = base_url
        self.timeout = timeout or config.timeout
        self.max_retries = max_retries or config.max_retries

        default_headers = {"User-Agent": DEFAULT_USER_AGENT}
        if channel_headers:
            default_headers.update(channel_headers)
        if headers:
            default_headers.update(headers)

        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=default_headers,
            timeout=httpx.Timeout(self.timeout),
            proxy=proxy,
            follow_redirects=True,
            # TODO: 未来可将连接池参数下沉到 SouWenConfig；当前使用保守默认
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30.0,
            ),
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
                method,
                url,
                resp.status_code,
                elapsed,
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
    def _parse_retry_after(value: str) -> float | None:
        """解析 Retry-After 头，支持秒数和 HTTP-date 两种格式"""
        try:
            return float(value)
        except ValueError:
            pass
        # RFC 7231: HTTP-date 格式，如 "Fri, 31 Dec 1999 23:59:59 GMT"
        from email.utils import parsedate_to_datetime

        try:
            dt = parsedate_to_datetime(value)
            import time

            delay = dt.timestamp() - time.time()
            return max(0, delay)
        except Exception:
            return None

    @staticmethod
    def _check_response(resp: httpx.Response, url: str) -> None:
        """检查响应状态码，抛出相应异常"""
        if resp.status_code == 401:
            raise AuthError(f"鉴权失败: {url}")
        if resp.status_code == 403:
            raise AuthError(f"权限不足: {url}")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = SouWenHttpClient._parse_retry_after(retry_after) if retry_after else None
            raise RateLimitError(f"限流触发: {url}", retry_after=wait)
        if resp.status_code == 404:
            return
        if resp.status_code >= 500:
            raise SourceUnavailableError(f"数据源服务器错误 ({resp.status_code}): {url}")
        if resp.status_code >= 400:
            raise SouWenError(f"请求失败 ({resp.status_code}): {url}")


class OAuthClient(SouWenHttpClient):
    """OAuth 2.0 Token 自动管理的 HTTP 客户端

    适用于 EPO OPS、CNIPA 等需要 OAuth 2.0 认证的数据源。
    实现了令牌缓存、自动刷新、并发安全的特性：
    - 令牌缓存：避免每次请求都重新获取
    - 自动刷新：提前 60 秒刷新，防止请求过程中 token 过期 (401 错误)
    - 并发安全：使用 asyncio.Lock 串行化令牌获取，避免并发调用打击 token 端点

    Args:
        base_url: API 基础 URL
        token_url: OAuth token 端点 URL
        client_id: OAuth client ID
        client_secret: OAuth client secret
        **kwargs: 其他参数（传给 SouWenHttpClient）

    Note:
        令牌锁使用懒加载（_get_token_lock），防止每次创建实例都分配新 Lock 对象。
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
        self._token_lock: asyncio.Lock | None = None

    def _get_token_lock(self) -> asyncio.Lock:
        """获取或创建令牌锁（懒加载）"""
        if self._token_lock is None:
            self._token_lock = asyncio.Lock()
        return self._token_lock

    async def _ensure_token(self) -> str:
        """确保有有效的 access token，过期则自动刷新

        刷新策略：
        - 检查缓存的 token 是否仍有效（还有 60+ 秒）
        - 若无效，获取令牌锁并向 token 端点发起请求
        - 使用二次检查锁模式，避免并发调用重复刷新
        - 提前 60 秒刷新，避免 token 在请求途中过期导致 401

        Returns:
            有效的 access token 字符串

        Raises:
            AuthError: token 获取失败或响应解析失败
        """
        if self._access_token and time.monotonic() < self._token_expires_at - 60:
            return self._access_token

        async with self._get_token_lock():
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

            try:
                token_data = resp.json()
            except Exception as e:
                raise AuthError(f"OAuth token 响应解析失败: {e}") from e

            access_token = token_data.get("access_token")
            if not access_token:
                raise AuthError(f"OAuth 响应缺少 access_token: {list(token_data.keys())}")

            self._access_token = access_token
            expires_in = token_data.get("expires_in", 1200)
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
