"""GET /sources — 列出当前可用数据源"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from souwen.server.auth import check_search_auth

router = APIRouter()


@router.get("/sources", dependencies=[Depends(check_search_auth)])
async def list_sources():
    """列出当前可用数据源 — 按类别分组。

    需要 API Key 或自托管配置但未设置的源不会返回，
    确保前端搜索页只展示真正可用的通道。
    """
    from souwen.config import get_config
    from souwen.models import ALL_SOURCES
    from souwen.source_registry import get_source

    cfg = get_config()

    def _is_usable(name: str, needs_key: bool) -> bool:
        if not cfg.is_source_enabled(name):
            return False
        if not needs_key:
            return True
        meta = get_source(name)
        if meta is None or meta.config_field is None:
            return True
        if meta.integration_type == "self_hosted":
            return bool(cfg.resolve_base_url(name) or getattr(cfg, meta.config_field, None))
        return bool(cfg.resolve_api_key(name, meta.config_field))

    return {
        category: [
            {"name": name, "needs_key": needs_key, "description": desc}
            for name, needs_key, desc in entries
            if _is_usable(name, needs_key)
        ]
        for category, entries in ALL_SOURCES.items()
    }
