"""SouWen API 路由定义"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, HTTPException

from souwen.server.auth import check_search_auth, require_auth
from souwen.server.limiter import rate_limit_search
from souwen.server.schemas import (
    ConfigReloadResponse,
    DoctorResponse,
    HttpBackendResponse,
    SearchPaperResponse,
    SearchPatentResponse,
    UpdateSourceConfigRequest,
)

logger = logging.getLogger("souwen.server")

router = APIRouter()

# ---------------------------------------------------------------------------
# 搜索端点 — 受 check_search_auth 保护（有密码时需认证，无密码时放行）
# ---------------------------------------------------------------------------


@router.get(
    "/search/paper",
    response_model=SearchPaperResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_paper(
    q: str = Query(..., description="搜索关键词"),
    sources: str = Query("openalex,arxiv", description="数据源，逗号分隔"),
    per_page: int = Query(10, ge=1, le=100, description="每页结果数"),
):
    """搜索学术论文"""
    from souwen.search import search_papers

    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    try:
        results = await search_papers(q, sources=source_list, per_page=per_page)
        return {
            "query": q,
            "sources": source_list,
            "results": [r.model_dump(mode="json") for r in results],
            "total": sum(len(r.results) for r in results),
        }
    except Exception:
        logger.exception("论文搜索失败: q=%s sources=%s", q, source_list)
        raise HTTPException(status_code=500, detail="搜索服务内部错误，请稍后重试")


@router.get(
    "/search/patent",
    response_model=SearchPatentResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_patent(
    q: str = Query(..., description="搜索关键词"),
    sources: str = Query("google_patents", description="数据源，逗号分隔"),
    per_page: int = Query(10, ge=1, le=100, description="每页结果数"),
):
    """搜索专利"""
    from souwen.search import search_patents

    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    try:
        results = await search_patents(q, sources=source_list, per_page=per_page)
        return {
            "query": q,
            "sources": source_list,
            "results": [r.model_dump(mode="json") for r in results],
            "total": sum(len(r.results) for r in results),
        }
    except Exception:
        logger.exception("专利搜索失败: q=%s sources=%s", q, source_list)
        raise HTTPException(status_code=500, detail="搜索服务内部错误，请稍后重试")


@router.get("/search/web", dependencies=[Depends(rate_limit_search), Depends(check_search_auth)])
async def api_search_web(
    q: str = Query(..., description="搜索关键词"),
    engines: str = Query("duckduckgo,bing", description="搜索引擎，逗号分隔"),
    max_results: int = Query(10, ge=1, le=50, description="每引擎最大结果数"),
):
    """搜索网页"""
    from souwen.web.search import web_search

    engine_list = [e.strip() for e in engines.split(",") if e.strip()]
    try:
        resp = await web_search(q, engines=engine_list, max_results_per_engine=max_results)
        return resp.model_dump(mode="json")
    except Exception:
        logger.exception("网页搜索失败: q=%s engines=%s", q, engine_list)
        raise HTTPException(status_code=500, detail="搜索服务内部错误，请稍后重试")


@router.get("/sources", dependencies=[Depends(check_search_auth)])
async def list_sources():
    """列出所有可用数据源"""
    from souwen.models import ALL_SOURCES

    return {
        category: [
            {"name": name, "needs_key": needs_key, "description": desc}
            for name, needs_key, desc in entries
        ]
        for category, entries in ALL_SOURCES.items()
    }


# ---------------------------------------------------------------------------
# 管理端点 — 始终需要 api_password 认证
# ---------------------------------------------------------------------------
admin_router = APIRouter(dependencies=[Depends(require_auth)])

_SECRET_KEYWORDS = {"key", "secret", "token", "password"}


def _is_secret_field(name: str) -> bool:
    return any(kw in name for kw in _SECRET_KEYWORDS)


@admin_router.get("/config")
async def get_config_view():
    """查看当前配置（敏感字段脱敏）"""
    from souwen.config import SouWenConfig, get_config

    cfg = get_config()
    result = {}
    for field_name in SouWenConfig.model_fields:
        val = getattr(cfg, field_name)
        if _is_secret_field(field_name) and val is not None:
            result[field_name] = "***"
        else:
            result[field_name] = val
    return result


@admin_router.post("/config/reload", response_model=ConfigReloadResponse)
async def reload_config_endpoint():
    """重新加载配置（YAML + .env）"""
    from souwen.config import reload_config

    cfg = reload_config()
    return {"status": "ok", "password_set": cfg.api_password is not None}


@admin_router.get("/doctor", response_model=DoctorResponse)
async def doctor_check():
    """数据源健康检查"""
    from souwen.doctor import check_all

    results = check_all()
    ok_count = sum(1 for r in results if r["status"] == "ok")
    return {
        "total": len(results),
        "ok": ok_count,
        "sources": results,
    }


# ---------------------------------------------------------------------------
# 数据源频道配置
# ---------------------------------------------------------------------------


@admin_router.get("/sources/config")
async def get_sources_config():
    """查看所有数据源的频道配置"""
    from souwen.config import get_config
    from souwen.source_registry import get_all_sources

    cfg = get_config()
    all_sources = get_all_sources()
    result: dict = {}
    for name, meta in all_sources.items():
        sc = cfg.get_source_config(name)
        entry: dict = {
            "enabled": sc.enabled,
            "proxy": sc.proxy,
            "http_backend": sc.http_backend,
            "base_url": sc.base_url,
            "has_api_key": bool(cfg.resolve_api_key(name, meta.config_field)),
            "headers": sc.headers,
            "params": sc.params,
            "category": meta.category,
            "tier": meta.tier,
            "is_scraper": meta.is_scraper,
            "description": meta.description,
        }
        result[name] = entry
    return result


@admin_router.get("/sources/config/{source_name}")
async def get_source_config(source_name: str):
    """查看单个数据源的频道配置"""
    from souwen.config import get_config
    from souwen.source_registry import get_source

    meta = get_source(source_name)
    if meta is None:
        raise HTTPException(404, f"未知数据源: {source_name}")

    cfg = get_config()
    sc = cfg.get_source_config(source_name)
    return {
        "name": source_name,
        "enabled": sc.enabled,
        "proxy": sc.proxy,
        "http_backend": sc.http_backend,
        "base_url": sc.base_url,
        "has_api_key": bool(cfg.resolve_api_key(source_name, meta.config_field)),
        "headers": sc.headers,
        "params": sc.params,
        "category": meta.category,
        "tier": meta.tier,
        "is_scraper": meta.is_scraper,
        "description": meta.description,
    }


@admin_router.put("/sources/config/{source_name}")
async def update_source_config(
    source_name: str,
    req: UpdateSourceConfigRequest,
):
    """更新单个数据源的频道配置（运行时，重启后需 YAML 持久化）

    使用 JSON 请求体传递参数，避免 API Key 泄露到 URL/日志中。
    """
    from souwen.config import SourceChannelConfig, get_config
    from souwen.source_registry import is_known_source

    if not is_known_source(source_name):
        raise HTTPException(404, f"未知数据源: {source_name}")

    _VALID_BACKENDS = {"auto", "curl_cffi", "httpx"}
    if req.http_backend is not None and req.http_backend not in _VALID_BACKENDS:
        raise HTTPException(400, f"无效的 http_backend: {req.http_backend}")

    cfg = get_config()
    sc = cfg.sources.get(source_name, SourceChannelConfig())

    if req.enabled is not None:
        sc.enabled = req.enabled
    if req.proxy is not None:
        sc.proxy = req.proxy
    if req.http_backend is not None:
        sc.http_backend = req.http_backend
    if req.base_url is not None:
        sc.base_url = req.base_url if req.base_url else None
    if req.api_key is not None:
        sc.api_key = req.api_key if req.api_key else None

    cfg.sources[source_name] = sc
    return {"status": "ok", "source": source_name}


# ---------------------------------------------------------------------------
# HTTP 后端配置（旧版兼容）
# ---------------------------------------------------------------------------

# 使用 BaseScraper 的引擎名称列表（可配置 HTTP 后端）
_SCRAPER_ENGINES = [
    "duckduckgo", "yahoo", "brave", "google", "bing",
    "startpage", "baidu", "mojeek", "yandex", "google_patents",
]


@admin_router.get("/http-backend", response_model=HttpBackendResponse)
async def get_http_backend():
    """查看 HTTP 后端配置"""
    from souwen.config import get_config
    from souwen.scraper.base import _HAS_CURL_CFFI

    cfg = get_config()
    return {
        "default": cfg.default_http_backend,
        "overrides": cfg.http_backend,
        "curl_cffi_available": _HAS_CURL_CFFI,
    }


@admin_router.put("/http-backend")
async def update_http_backend(
    default: str | None = Query(None, description="全局默认: auto | curl_cffi | httpx"),
    source: str | None = Query(None, description="要覆盖的源名称"),
    backend: str | None = Query(None, description="后端: auto | curl_cffi | httpx"),
):
    """更新 HTTP 后端配置（运行时生效，重启后需通过 YAML/env 持久化）"""
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


# ---------------------------------------------------------------------------
# WARP 代理管理
# ---------------------------------------------------------------------------


@admin_router.get("/warp")
async def warp_status():
    """获取 WARP 代理状态"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    return mgr.get_status()


@admin_router.post("/warp/enable")
async def warp_enable(
    mode: str = Query("auto", description="模式: auto | wireproxy | kernel"),
    socks_port: int = Query(1080, ge=1, le=65535, description="SOCKS5 端口"),
    endpoint: str | None = Query(None, description="自定义 WARP Endpoint"),
):
    """启用 WARP 代理"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    result = await mgr.enable(mode=mode, socks_port=socks_port, endpoint=endpoint)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@admin_router.post("/warp/disable")
async def warp_disable():
    """禁用 WARP 代理"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    result = await mgr.disable()
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
