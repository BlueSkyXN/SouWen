"""Wayback Machine 写入端点 — /admin/wayback/save

文件用途：
    存档（Save）属于会触发外网写入的操作，需要管理认证；查询类（CDX、availability）
    在 routes/wayback.py 中以访客权限暴露。

模块依赖：
    - WaybackSaveRequest / WaybackSaveResponse  请求/响应模型
    - souwen.web.wayback.WaybackClient          实际调用
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from souwen.server.routes._common import logger
from souwen.server.schemas import WaybackSaveRequest, WaybackSaveResponse

router = APIRouter()


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
