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
    from souwen.registry import all_adapters, public_source_catalog
    from souwen.registry.adapter import FETCH_DOMAIN
    from souwen.registry.meta import has_required_credentials

    cfg = get_config()

    # TODO(PR6): /sources 公开 contract 切到正式 catalog key 后删除这层临时适配。
    category_map = {
        "paper": "paper",
        "patent": "patent",
        "web_general": "general",
        "web_professional": "professional",
        "social": "social",
        "office": "office",
        "developer": "developer",
        "knowledge": "wiki",
        "cn_tech": "cn_tech",
        "video": "video",
        "archive": "fetch",
        "fetch": "fetch",
    }

    def _source_item(name: str, meta) -> dict:
        return {
            "name": name,
            "needs_key": meta.needs_config,
            "key_requirement": meta.auth_requirement,
            "auth_requirement": meta.auth_requirement,
            "credential_fields": list(meta.credential_fields),
            "optional_credential_effect": meta.optional_credential_effect,
            "integration_type": meta.integration_type,
            "risk_level": meta.risk_level,
            "risk_reasons": sorted(meta.risk_reasons),
            "distribution": meta.distribution,
            "package_extra": meta.package_extra,
            "stability": meta.stability,
            "usage_note": meta.usage_note,
            "default_enabled": meta.default_enabled,
            "description": meta.description,
        }

    def _append_visible_source(
        result: dict[str, list[dict]], category: str, name: str, meta
    ) -> None:
        item = _source_item(name, meta)
        if not any(existing["name"] == name for existing in result[category]):
            result[category].append(item)

    result: dict[str, list[dict]] = {category: [] for category in SOURCE_CATEGORY_ORDER}
    adapters = all_adapters()
    for name, meta in public_source_catalog().items():
        if not cfg.is_source_enabled(name):
            continue
        if not has_required_credentials(cfg, name, meta):
            continue
        category = category_map[meta.category]
        _append_visible_source(result, category, name, meta)
        adapter = adapters.get(name)
        if adapter is not None and FETCH_DOMAIN in adapter.extra_domains:
            _append_visible_source(result, "fetch", name, meta)
    return result
