"""GET /sources — 列出当前可用数据源"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from souwen.server.auth import check_search_auth
from souwen.server.schemas import SOURCE_CATEGORY_ORDER, SourcesResponse

router = APIRouter()


@router.get("/sources", response_model=SourcesResponse, dependencies=[Depends(check_search_auth)])
async def list_sources():
    """列出当前可用数据源 — 按类别分组。

    需要 API Key 或自托管配置但未设置的源不会返回，
    确保前端搜索页只展示真正可用的通道。
    """
    from souwen.config import get_config
    from souwen.registry import as_all_sources_dict
    from souwen.source_registry import get_source, has_required_credentials

    cfg = get_config()
    all_sources = as_all_sources_dict()

    def _is_usable(name: str) -> bool:
        if not cfg.is_source_enabled(name):
            return False
        meta = get_source(name)
        if meta is None:
            return False
        return has_required_credentials(cfg, name, meta)

    def _source_item(name: str) -> dict | None:
        meta = get_source(name)
        if meta is None:
            return None
        return {
            "name": name,
            "needs_key": meta.needs_config,
            "key_requirement": meta.key_requirement,
            "auth_requirement": meta.auth_requirement,
            "credential_fields": list(meta.credential_fields),
            "optional_credential_effect": meta.optional_credential_effect,
            "integration_type": meta.integration_type,
            "risk_level": meta.risk_level,
            "risk_reasons": sorted(meta.risk_reasons),
            "distribution": meta.distribution,
            "package_extra": meta.package_extra,
            "stability": meta.stability,
            "default_enabled": meta.default_enabled,
            "description": meta.description,
        }

    result: dict[str, list[dict]] = {category: [] for category in SOURCE_CATEGORY_ORDER}
    for category, entries in all_sources.items():
        result.setdefault(category, [])
        for name, _needs_key, _desc in entries:
            if not _is_usable(name):
                continue
            item = _source_item(name)
            if item is not None:
                result[category].append(item)
    return result
