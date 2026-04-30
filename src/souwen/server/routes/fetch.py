"""内容抓取端点 — POST /fetch、GET /links、GET /sitemap"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from souwen.registry import fetch_providers
from souwen.server.auth import require_auth
from souwen.server.limiter import rate_limit_search
from souwen.server.routes._common import logger
from souwen.server.schemas import FetchRequest

router = APIRouter()


def _valid_fetch_provider_names() -> frozenset[str]:
    return frozenset(adapter.name for adapter in fetch_providers())


@router.post(
    "/fetch",
    dependencies=[Depends(rate_limit_search), Depends(require_auth)],
)
async def fetch_content_endpoint(body: FetchRequest):
    """抓取网页内容。"""
    from souwen.web.fetch import fetch_content

    valid_fetch_providers = _valid_fetch_provider_names()
    if body.provider not in valid_fetch_providers:
        raise HTTPException(
            status_code=400,
            detail=f"无效提供者: {body.provider}，可选: {', '.join(sorted(valid_fetch_providers))}",
        )

    try:
        resp = await asyncio.wait_for(
            fetch_content(
                urls=body.urls,
                providers=[body.provider],
                timeout=body.timeout,
                selector=body.selector,
                start_index=body.start_index,
                max_length=body.max_length,
                respect_robots_txt=body.respect_robots_txt,
            ),
            timeout=body.timeout + 15,
        )
        return {
            "urls": resp.urls,
            "results": [r.model_dump(mode="json") for r in resp.results],
            "total": resp.total,
            "total_ok": resp.total_ok,
            "total_failed": resp.total_failed,
            "provider": resp.provider,
            "meta": resp.meta,
        }
    except asyncio.TimeoutError:
        logger.warning("内容抓取超时: provider=%s urls=%d", body.provider, len(body.urls))
        raise HTTPException(status_code=504, detail=f"抓取超时（{body.timeout}s）")
    except Exception:
        logger.warning("内容抓取内部错误: provider=%s", body.provider, exc_info=True)
        raise


@router.get(
    "/links",
    dependencies=[Depends(rate_limit_search), Depends(require_auth)],
)
async def extract_links_endpoint(
    url: str = Query(..., description="目标页面 URL"),
    base_url_filter: str | None = Query(None, alias="base_url", description="URL 前缀过滤"),
    limit: int = Query(100, ge=1, le=1000, description="最大返回链接数"),
):
    """提取页面链接 — 返回去重、SSRF 过滤后的链接列表。"""
    from souwen.web.links import extract_links

    try:
        result = await asyncio.wait_for(
            extract_links(url=url, base_url_filter=base_url_filter, limit=limit),
            timeout=30,
        )
        return result.model_dump(mode="json")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="链接提取超时")


@router.get(
    "/sitemap",
    dependencies=[Depends(rate_limit_search), Depends(require_auth)],
)
async def parse_sitemap_endpoint(
    url: str = Query(..., description="Sitemap URL 或站点根 URL"),
    discover: bool = Query(False, description="自动发现 sitemap（从 robots.txt 等）"),
    limit: int = Query(1000, ge=1, le=50000, description="最大返回条目数"),
):
    """解析 sitemap.xml — 提取站点 URL 列表。"""
    from souwen.web.sitemap import discover_sitemap, parse_sitemap

    try:
        if discover:
            result = await asyncio.wait_for(
                discover_sitemap(url, max_entries=limit),
                timeout=60,
            )
        else:
            result = await asyncio.wait_for(
                parse_sitemap(url, max_entries=limit),
                timeout=60,
            )
        return result.model_dump(mode="json")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Sitemap 解析超时")
