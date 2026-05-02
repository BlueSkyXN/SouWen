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

    def _credential_value(name: str, field: str, primary_field: str | None) -> str | None:
        if field == primary_field:
            return cfg.resolve_api_key(name, field)
        return getattr(cfg, field, None)

    def _has_required_credentials(name: str, meta) -> bool:
        if meta.auth_requirement == "none" or meta.auth_requirement == "optional":
            return True
        fields = meta.credential_fields
        if not fields:
            return True
        for field in fields:
            if meta.auth_requirement == "self_hosted" and field == meta.config_field:
                value = cfg.resolve_base_url(name) or getattr(cfg, field, None)
            else:
                value = _credential_value(name, field, meta.config_field)
            if not value:
                return False
        return True

    def _is_usable(name: str) -> bool:
        if not cfg.is_source_enabled(name):
            return False
        meta = get_source(name)
        if meta is None:
            return True
        return _has_required_credentials(name, meta)

    def _source_item(name: str, needs_key: bool, desc: str) -> dict:
        meta = get_source(name)
        if meta is None:
            return {"name": name, "needs_key": needs_key, "description": desc}
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

    return {
        category: [
            _source_item(name, needs_key, desc)
            for name, needs_key, desc in entries
            if _is_usable(name)
        ]
        for category, entries in ALL_SOURCES.items()
    }
