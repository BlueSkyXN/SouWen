"""Wayback Machine 公开查询端点 — CDX / Availability"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from souwen.server.auth import check_search_auth
from souwen.server.limiter import rate_limit_search
from souwen.server.routes._common import logger
from souwen.server.schemas import (
    WaybackAvailabilityResponse,
    WaybackCDXApiResponse,
)

router = APIRouter()


@router.get(
    "/wayback/cdx",
    response_model=WaybackCDXApiResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_wayback_cdx(
    url: str = Query(..., description="查询 URL (支持通配符 *)"),
    from_date: str | None = Query(None, alias="from", description="起始日期 (YYYYMMDD)"),
    to_date: str | None = Query(None, alias="to", description="结束日期 (YYYYMMDD)"),
    limit: int = Query(100, ge=1, le=10000, description="最大快照数"),
    filter_status: int | None = Query(None, description="HTTP 状态码过滤 (如 200)"),
    collapse: str | None = Query(None, description="去重规则 (如 timestamp:8 按天去重)"),
    timeout: float | None = Query(None, ge=1, le=120, description="端点硬超时（秒），超时返回 504"),
):
    """查询 Wayback Machine CDX — URL 历史快照列表。"""
    from souwen.web.wayback import WaybackClient

    inner_timeout = timeout or 60.0
    try:
        client = WaybackClient()
        coro = client.query_snapshots(
            url=url,
            from_date=from_date,
            to_date=to_date,
            filter_status=[filter_status] if filter_status is not None else None,
            limit=limit,
            collapse=collapse,
            timeout=inner_timeout,
        )
        if timeout is not None:
            resp = await asyncio.wait_for(coro, timeout=timeout + 5)
        else:
            resp = await coro
        return {
            "url": url,
            "snapshots": [s.model_dump(mode="json") for s in resp.snapshots],
            "total": resp.total,
        }
    except asyncio.TimeoutError:
        logger.warning("Wayback CDX 超时: url=%s timeout=%ss", url, timeout)
        raise HTTPException(status_code=504, detail=f"CDX 查询超时（{timeout}s）")
    except Exception:
        logger.warning("Wayback CDX 错误: url=%s", url, exc_info=True)
        raise


@router.get(
    "/wayback/check",
    response_model=WaybackAvailabilityResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_wayback_check(
    url: str = Query(..., description="目标 URL"),
    timestamp: str | None = Query(None, description="目标时间戳 (YYYYMMDD 或 YYYYMMDDHHMMSS)"),
    timeout: float | None = Query(None, ge=1, le=60, description="端点硬超时（秒），超时返回 504"),
):
    """检查 URL 在 Wayback Machine 中的可用性。"""
    from souwen.web.wayback import WaybackClient

    inner_timeout = timeout or 30.0
    try:
        client = WaybackClient()
        coro = client.check_availability(url=url, timestamp=timestamp, timeout=inner_timeout)
        if timeout is not None:
            resp = await asyncio.wait_for(coro, timeout=timeout + 5)
        else:
            resp = await coro
        return {
            "url": url,
            "available": resp.available,
            "snapshot_url": resp.snapshot_url,
            "timestamp": resp.timestamp,
            "status": resp.status_code,
        }
    except asyncio.TimeoutError:
        logger.warning("Wayback availability 超时: url=%s timeout=%ss", url, timeout)
        raise HTTPException(status_code=504, detail=f"可用性检查超时（{timeout}s）")
    except Exception:
        logger.warning("Wayback availability 错误: url=%s", url, exc_info=True)
        raise
