"""HTTP 后端配置（旧版兼容）— /admin/http-backend"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from souwen.server.schemas import HttpBackendResponse

router = APIRouter()

# 使用 BaseScraper 的引擎名称列表（可配置 HTTP 后端）
_SCRAPER_ENGINES = [
    "duckduckgo",
    "yahoo",
    "brave",
    "google",
    "bing",
    "startpage",
    "baidu",
    "mojeek",
    "yandex",
    "google_patents",
]


@router.get("/http-backend", response_model=HttpBackendResponse)
async def get_http_backend():
    """查看 HTTP 后端配置。"""
    from souwen.config import get_config
    from souwen.scraper.base import _HAS_CURL_CFFI

    cfg = get_config()
    return {
        "default": cfg.default_http_backend,
        "overrides": cfg.http_backend,
        "curl_cffi_available": _HAS_CURL_CFFI,
    }


@router.put("/http-backend")
async def update_http_backend(
    default: str | None = Query(None, description="全局默认: auto | curl_cffi | httpx"),
    source: str | None = Query(None, description="要覆盖的源名称"),
    backend: str | None = Query(None, description="后端: auto | curl_cffi | httpx"),
):
    """更新 HTTP 后端配置（运行时生效）。"""
    from souwen.config import get_config

    _VALID = {"auto", "curl_cffi", "httpx"}
    cfg = get_config()

    if default is not None:
        if default not in _VALID:
            raise HTTPException(400, f"无效的默认后端: {default}，可选: {', '.join(_VALID)}")
        cfg.default_http_backend = default

    if source is not None and backend is not None:
        if backend not in _VALID:
            raise HTTPException(400, f"无效的后端: {backend}，可选: {', '.join(_VALID)}")
        if source not in _SCRAPER_ENGINES:
            raise HTTPException(
                400,
                f"未知的爬虫源: {source}，可选: {', '.join(_SCRAPER_ENGINES)}",
            )
        if backend == "auto":
            cfg.http_backend.pop(source, None)
        else:
            cfg.http_backend[source] = backend

    return {
        "status": "ok",
        "default": cfg.default_http_backend,
        "overrides": cfg.http_backend,
    }
