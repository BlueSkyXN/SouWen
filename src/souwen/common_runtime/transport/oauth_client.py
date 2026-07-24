"""OAuth 2.0 client-credentials transport over explicit HTTP options."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from .errors import AuthError
from .http_client import HttpTransport, RequestRetryPolicy

logger = logging.getLogger("souwen.http")


class OAuthTransport(HttpTransport):
    """Explicit-options OAuth 2.0 client-credentials transport."""

    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str],
        timeout: int | float,
        max_retries: int,
        proxy: str | None,
        follow_redirects: bool,
        token_url: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        super().__init__(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            max_retries=max_retries,
            proxy=proxy,
            follow_redirects=follow_redirects,
        )
        self._initialize_oauth(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
        )

    def _initialize_oauth(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
    ) -> None:
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

            logger.debug("正在获取 OAuth token")
            resp = await self._client.post(
                self.token_url,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
            )
            if resp.status_code != 200:
                raise AuthError(f"OAuth token 获取失败: HTTP {resp.status_code}")

            try:
                token_data = resp.json()
            except Exception as e:
                raise AuthError("OAuth token 响应解析失败") from e

            access_token = token_data.get("access_token")
            if not access_token:
                raise AuthError("OAuth 响应缺少 access_token")

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
        retry_policy: RequestRetryPolicy = "default",
    ) -> httpx.Response:
        """带 OAuth token 的 GET 请求"""
        self._validate_retry_policy(retry_policy)
        token = await self._ensure_token()
        auth_headers = {"Authorization": f"Bearer {token}"}
        if headers:
            auth_headers.update(headers)
        return await super().get(
            url,
            params=params,
            headers=auth_headers,
            retry_policy=retry_policy,
        )

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_policy: RequestRetryPolicy = "default",
    ) -> httpx.Response:
        """带 OAuth token 的 POST 请求"""
        self._validate_retry_policy(retry_policy)
        token = await self._ensure_token()
        auth_headers = {"Authorization": f"Bearer {token}"}
        if headers:
            auth_headers.update(headers)
        return await super().post(
            url,
            json=json,
            data=data,
            headers=auth_headers,
            retry_policy=retry_policy,
        )
