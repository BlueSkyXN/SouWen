"""SouWen API 路由定义"""

from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException

router = APIRouter()


@router.get("/search/paper")
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


@router.get("/search/patent")
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


@router.get("/search/web")
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


@router.get("/sources")
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
