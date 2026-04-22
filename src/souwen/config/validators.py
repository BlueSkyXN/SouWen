"""代理 URL 校验工具

从 souwen.config 拆分而来,提供安全代理 URL 校验.
"""

from __future__ import annotations

from urllib.parse import urlparse

# 仅允许常见代理协议;禁止 file:// / javascript: 等潜在危险 scheme
_ALLOWED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h", "socks4", "socks4a"}


def _validate_proxy_url(url: str | None) -> str | None:
    """校验显式代理 URL 合法性

    非字符串 / 空串返回 None;非法则抛 ValueError.

    Args:
        url: 代理 URL 字符串

    Returns:
        合法的 URL 字符串,或 None(空值)

    Raises:
        ValueError: URL 格式错误或协议不被允许
    """
    if url is None:
        return None
    if not isinstance(url, str):
        raise ValueError(f"代理 URL 必须为字符串: {url!r}")
    u = url.strip()
    if not u:
        return None
    try:
        parsed = urlparse(u)
    except Exception as e:
        raise ValueError(f"非法的代理 URL: {url!r} ({e})") from e
    if parsed.scheme.lower() not in _ALLOWED_PROXY_SCHEMES:
        raise ValueError(
            f"不支持的代理协议 {parsed.scheme!r}: {url!r}(允许:{sorted(_ALLOWED_PROXY_SCHEMES)})"
        )
    if not parsed.hostname:
        raise ValueError(f"代理 URL 缺少 host: {url!r}")
    return u
