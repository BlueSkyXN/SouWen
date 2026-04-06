"""SouWen API 路由定义"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException

from souwen.server.auth import check_search_auth, require_auth

router = APIRouter()

# ---------------------------------------------------------------------------
# 搜索端点 — 受 check_search_auth 保护（有密码时需认证，无密码时放行）
# ---------------------------------------------------------------------------


@router.get("/search/paper", dependencies=[Depends(check_search_auth)])
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/patent", dependencies=[Depends(check_search_auth)])
async def api_search_patent(
    q: str = Query(..., description="搜索关键词"),
    sources: str = Query("patentsview,pqai", description="数据源，逗号分隔"),
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/web", dependencies=[Depends(check_search_auth)])
async def api_search_web(
    q: str = Query(..., description="搜索关键词"),
    engines: str = Query("duckduckgo,yahoo,brave", description="搜索引擎，逗号分隔"),
    max_results: int = Query(10, ge=1, le=50, description="每引擎最大结果数"),
):
    """搜索网页"""
    from souwen.web.search import web_search

    engine_list = [e.strip() for e in engines.split(",") if e.strip()]
    try:
        resp = await web_search(q, engines=engine_list, max_results_per_engine=max_results)
        return resp.model_dump(mode="json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    from souwen.config import get_config

    cfg = get_config()
    result = {}
    for field_name in cfg.model_fields:
        val = getattr(cfg, field_name)
        if _is_secret_field(field_name) and val is not None:
            result[field_name] = "***"
        else:
            result[field_name] = val
    return result


@admin_router.post("/config/reload")
async def reload_config_endpoint():
    """重新加载配置（YAML + .env）"""
    from souwen.config import reload_config

    cfg = reload_config()
    return {"status": "ok", "password_set": cfg.api_password is not None}


@admin_router.get("/doctor")
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
