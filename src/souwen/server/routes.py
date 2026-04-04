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
    engines: str = Query(
        "duckduckgo,yahoo,brave", description="搜索引擎，逗号分隔"
    ),
    max_results: int = Query(10, ge=1, le=50, description="每引擎最大结果数"),
):
    """搜索网页"""
    from souwen.web.search import web_search

    engine_list = [e.strip() for e in engines.split(",") if e.strip()]
    try:
        resp = await web_search(
            q, engines=engine_list, max_results_per_engine=max_results
        )
        return resp.model_dump(mode="json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources")
async def list_sources():
    """列出所有可用数据源"""
    return {
        "paper": [
            {"name": "openalex", "needs_key": False, "description": "OpenAlex 开放学术图谱"},
            {"name": "semantic_scholar", "needs_key": False, "description": "Semantic Scholar (可选Key提速)"},
            {"name": "crossref", "needs_key": False, "description": "Crossref DOI 权威源"},
            {"name": "arxiv", "needs_key": False, "description": "arXiv 预印本"},
            {"name": "dblp", "needs_key": False, "description": "DBLP 计算机科学索引"},
            {"name": "core", "needs_key": True, "description": "CORE 全文开放获取"},
            {"name": "pubmed", "needs_key": False, "description": "PubMed 生物医学"},
            {"name": "unpaywall", "needs_key": False, "description": "Unpaywall OA 链接查找"},
        ],
        "patent": [
            {"name": "patentsview", "needs_key": False, "description": "PatentsView/USPTO 美国专利"},
            {"name": "pqai", "needs_key": False, "description": "PQAI 语义专利检索"},
            {"name": "epo_ops", "needs_key": True, "description": "EPO OPS 欧洲专利 (OAuth)"},
            {"name": "uspto_odp", "needs_key": True, "description": "USPTO ODP 官方 API"},
            {"name": "the_lens", "needs_key": True, "description": "The Lens 全球专利+论文"},
            {"name": "cnipa", "needs_key": True, "description": "CNIPA 中国知识产权局 (OAuth)"},
            {"name": "patsnap", "needs_key": True, "description": "PatSnap 智慧芽"},
            {"name": "google_patents", "needs_key": False, "description": "Google Patents (爬虫)"},
        ],
        "web": [
            {"name": "duckduckgo", "needs_key": False, "description": "DuckDuckGo (爬虫)"},
            {"name": "yahoo", "needs_key": False, "description": "Yahoo (爬虫)"},
            {"name": "brave", "needs_key": False, "description": "Brave (爬虫)"},
            {"name": "google", "needs_key": False, "description": "Google (爬虫, 高风险)"},
            {"name": "bing", "needs_key": False, "description": "Bing (爬虫)"},
            {"name": "searxng", "needs_key": False, "description": "SearXNG 元搜索 (需自建)"},
            {"name": "tavily", "needs_key": True, "description": "Tavily AI 搜索"},
            {"name": "exa", "needs_key": True, "description": "Exa 语义搜索"},
            {"name": "serper", "needs_key": True, "description": "Serper Google SERP API"},
            {"name": "brave_api", "needs_key": True, "description": "Brave 官方 API"},
        ],
    }
