"""全局代理配置 — /admin/proxy"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from souwen.server.routes._common import (
    redact_secret_text,
    redact_secret_url,
    reject_redacted_placeholder,
)
from souwen.server.schemas import (
    ProxyConfigResponse,
    ProxyConfigUpdateResponse,
    UpdateProxyConfigRequest,
)

router = APIRouter()


def _safe_proxy_response(
    proxy: str | None,
    proxy_pool: list[str],
    *,
    socks_supported: bool | None = None,
) -> dict:
    """Return proxy config with URL credentials and secret params redacted."""
    response = {
        "proxy": redact_secret_url(proxy) if proxy else None,
        "proxy_pool": [redact_secret_url(url) for url in proxy_pool],
    }
    if socks_supported is not None:
        response["socks_supported"] = socks_supported
    return response


@router.get("/proxy", response_model=ProxyConfigResponse)
async def get_proxy_config():
    """查看全局代理配置。"""
    from souwen.config import get_config

    cfg = get_config()
    socks_ok = False
    try:
        import socksio  # noqa: F401

        socks_ok = True
    except ImportError:
        pass
    return _safe_proxy_response(cfg.proxy, list(cfg.proxy_pool), socks_supported=socks_ok)


@router.put("/proxy", response_model=ProxyConfigUpdateResponse)
async def update_proxy_config(req: UpdateProxyConfigRequest):
    """更新全局代理配置（运行时生效）。"""
    from souwen.config import _validate_proxy_url, get_config

    cfg = get_config()

    if req.proxy is not None:
        reject_redacted_placeholder(req.proxy, "proxy")
        try:
            validated_proxy = _validate_proxy_url(req.proxy)
        except ValueError as e:
            raise HTTPException(422, redact_secret_text(str(e)) or "代理 URL 无效")
        if validated_proxy:
            parsed = urlparse(validated_proxy)
            if parsed.scheme.lower() in ("socks5", "socks5h", "socks4", "socks4a"):
                try:
                    import socksio  # noqa: F401
                except ImportError:
                    safe_proxy = redact_secret_url(validated_proxy)
                    raise HTTPException(
                        422,
                        f"SOCKS 代理需要安装 httpx[socks] (socksio): {safe_proxy}",
                    )
            cfg.proxy = validated_proxy
        else:
            cfg.proxy = None

    if req.proxy_pool is not None:
        validated = []
        for index, url in enumerate(req.proxy_pool):
            reject_redacted_placeholder(url, f"proxy_pool[{index}]")
            try:
                v = _validate_proxy_url(url)
                if not v:
                    raise HTTPException(422, f"proxy_pool[{index}] 不能是空字符串")
                if v:
                    validated.append(v)
            except ValueError as e:
                detail = redact_secret_text(str(e)) or "代理 URL 无效"
                raise HTTPException(422, f"代理池 URL 无效: {detail}")
        for url in validated:
            parsed = urlparse(url)
            if parsed.scheme.lower() in ("socks5", "socks5h", "socks4", "socks4a"):
                try:
                    import socksio  # noqa: F401
                except ImportError:
                    safe_url = redact_secret_url(url)
                    raise HTTPException(
                        422,
                        f"代理池中含 SOCKS 代理但未安装 httpx[socks] (socksio): {safe_url}",
                    )
        cfg.proxy_pool = validated

    return {"status": "ok", **_safe_proxy_response(cfg.proxy, list(cfg.proxy_pool))}
