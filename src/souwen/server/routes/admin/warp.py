"""WARP 代理管理与 Wayback 写入 — /admin/warp/*、/admin/wayback/save"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from souwen.server.routes._common import logger
from souwen.server.schemas import WaybackSaveRequest, WaybackSaveResponse

router = APIRouter()


@router.get("/warp")
async def warp_status():
    """获取 WARP 代理状态 — 包括模式、IP、PID 等。"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    return mgr.get_status()


@router.post("/warp/enable")
async def warp_enable(
    mode: str = Query("auto", description="模式: auto | wireproxy | kernel"),
    socks_port: int = Query(1080, ge=1, le=65535, description="SOCKS5 端口"),
    endpoint: str | None = Query(None, description="自定义 WARP Endpoint"),
):
    """启用 WARP 代理 — 支持 auto、wireproxy、kernel 三种模式。"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    result = await mgr.enable(mode=mode, socks_port=socks_port, endpoint=endpoint)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/warp/disable")
async def warp_disable():
    """禁用 WARP 代理 — 清理进程和网络配置。"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    result = await mgr.disable()
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Wayback Machine — 写入操作（管理认证）
# ---------------------------------------------------------------------------


@router.post("/wayback/save", response_model=WaybackSaveResponse)
async def api_wayback_save(body: WaybackSaveRequest):
    """触发 Wayback Machine 立即存档 — 需要管理认证。"""
    from souwen.web.wayback import WaybackClient

    try:
        client = WaybackClient()
        resp = await asyncio.wait_for(
            client.save_page(url=body.url, timeout=body.timeout),
            timeout=body.timeout + 15,
        )
        return {
            "url": body.url,
            "success": resp.success,
            "snapshot_url": resp.snapshot_url,
            "timestamp": resp.timestamp,
            "error": resp.error,
        }
    except asyncio.TimeoutError:
        logger.warning("Wayback save 超时: url=%s timeout=%ss", body.url, body.timeout)
        raise HTTPException(status_code=504, detail=f"存档超时（{body.timeout}s）")
    except Exception:
        logger.warning("Wayback save 错误: url=%s", body.url, exc_info=True)
        raise
