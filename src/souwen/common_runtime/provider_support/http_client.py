"""统一 HTTP 客户端"""

from __future__ import annotations

from typing import Any

from souwen import __version__
from souwen.common_runtime.transport import (
    AuthError as AuthError,
    HttpTransport,
    OAuthTransport,
    RateLimitError as RateLimitError,
    RequestRetryPolicy as RequestRetryPolicy,
    SourceUnavailableError as SourceUnavailableError,
    SouWenError as SouWenError,
)
from souwen.config import get_config
from souwen.common_runtime.channel_overrides import (
    reviewed_source_max_retries,
    reviewed_source_proxy,
    reviewed_source_timeout_seconds,
    source_channel_overrides_enabled,
)

DEFAULT_USER_AGENT = (
    f"SouWen/{__version__} (Academic & Patent Search Tool; https://github.com/BlueSkyXN/SouWen)"
)


class SouWenHttpClient(HttpTransport):
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
        follow_redirects: 是否允许 httpx 自动跟随重定向
        resolve_source_base_url: source_name 存在时是否允许频道配置覆盖显式 base_url
    """

    def __init__(
        self,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        source_name: str | None = None,
        follow_redirects: bool = True,
        resolve_source_base_url: bool = True,
    ):
        config = get_config()

        # 频道配置可覆盖 base_url
        overrides_enabled = source_channel_overrides_enabled()
        if source_name and overrides_enabled:
            if resolve_source_base_url:
                base_url = config.resolve_base_url(source_name, default=base_url)
            proxy = config.resolve_proxy(source_name)
            channel_headers = config.resolve_headers(source_name)
        elif not overrides_enabled:
            proxy = reviewed_source_proxy()
            channel_headers = {}
        else:
            proxy = config.get_proxy()
            channel_headers = {}

        default_headers = {"User-Agent": DEFAULT_USER_AGENT}
        if channel_headers:
            default_headers.update(channel_headers)
        if headers:
            default_headers.update(headers)

        reviewed_timeout = reviewed_source_timeout_seconds() if not overrides_enabled else None
        reviewed_retries = reviewed_source_max_retries() if not overrides_enabled else None
        super().__init__(
            base_url=base_url,
            headers=default_headers,
            timeout=timeout or reviewed_timeout or config.timeout,
            max_retries=max_retries or reviewed_retries or config.max_retries,
            proxy=proxy,
            follow_redirects=follow_redirects,
        )


class OAuthClient(OAuthTransport, SouWenHttpClient):
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
        SouWenHttpClient.__init__(self, base_url=base_url, **kwargs)
        self._initialize_oauth(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
        )
