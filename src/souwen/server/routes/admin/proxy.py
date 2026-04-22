"""全局代理配置 — /admin/proxy"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from souwen.server.schemas import ProxyConfigResponse, UpdateProxyConfigRequest

router = APIRouter()


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
    return {
        "proxy": cfg.proxy,
        "proxy_pool": list(cfg.proxy_pool),
        "socks_supported": socks_ok,
    }


@router.put("/proxy")
async def update_proxy_config(req: UpdateProxyConfigRequest):
    """更新全局代理配置（运行时生效）。"""
    from souwen.config import _validate_proxy_url, get_config

    cfg = get_config()

    if req.proxy is not None:
        if req.proxy:
            try:
                _validate_proxy_url(req.proxy)
            except ValueError as e:
                raise HTTPException(422, str(e))
            parsed = urlparse(req.proxy)
            if parsed.scheme.lower() in ("socks5", "socks5h", "socks4", "socks4a"):
                try:
                    import socksio  # noqa: F401
                except ImportError:
                    raise HTTPException(
                        422,
                        f"SOCKS 代理需要安装 httpx[socks] (socksio): {req.proxy}",
                    )
            cfg.proxy = req.proxy
        else:
            cfg.proxy = None

    if req.proxy_pool is not None:
        validated = []
        for url in req.proxy_pool:
            try:
                v = _validate_proxy_url(url)
                if v:
                    validated.append(v)
            except ValueError as e:
                raise HTTPException(422, f"代理池 URL 无效: {e}")
        for url in validated:
            parsed = urlparse(url)
            if parsed.scheme.lower() in ("socks5", "socks5h", "socks4", "socks4a"):
                try:
                    import socksio  # noqa: F401
                except ImportError:
                    raise HTTPException(
                        422,
                        f"代理池中含 SOCKS 代理但未安装 httpx[socks] (socksio): {url}",
                    )
        cfg.proxy_pool = validated

    return {
        "status": "ok",
        "proxy": cfg.proxy,
        "proxy_pool": list(cfg.proxy_pool),
    }
