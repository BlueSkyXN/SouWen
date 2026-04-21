"""facade/archive.py — Wayback Machine 归档门面

薄封装 `souwen.web.wayback.WaybackClient`，把 v0 的入口统一在 facade 层。
v1 API 暴露为：
  - archive_lookup(url, ...) —— CDX 检索历史快照
  - archive_check(url)       —— 有/无存档快速查询
  - archive_save(url, ...)   —— Save Page Now 触发存档
  - archive_fetch(url, ...)  —— 抓取历史快照内容
"""

from __future__ import annotations

from typing import Any


async def archive_lookup(
    url: str,
    from_date: str | None = None,
    to_date: str | None = None,
    **kwargs: Any,
):
    """CDX 查询：返回 URL 的历史快照列表。"""
    from souwen.web.wayback import WaybackClient

    async with WaybackClient() as client:
        return await client.query_snapshots(
            url,
            from_date=from_date,
            to_date=to_date,
            **kwargs,
        )


async def archive_check(url: str, timestamp: str | None = None, timeout: float = 30.0):
    """快速判断 URL 是否有归档。"""
    from souwen.web.wayback import WaybackClient

    async with WaybackClient() as client:
        return await client.check_availability(url, timestamp=timestamp, timeout=timeout)


async def archive_save(url: str, timeout: float = 60.0):
    """触发 Wayback Save Page Now 存档。"""
    from souwen.web.wayback import WaybackClient

    async with WaybackClient() as client:
        return await client.save_page(url, timeout=timeout)


async def archive_fetch(url: str, timeout: float = 30.0):
    """抓取 URL 的 Wayback 存档副本（走 Wayback 缓存代理）。"""
    from souwen.web.wayback import WaybackClient

    async with WaybackClient() as client:
        return await client.fetch(url, timeout=timeout)
