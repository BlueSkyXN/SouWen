"""数据源频道配置 — /admin/sources/config[/{name}]"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from souwen.server.schemas import UpdateSourceConfigRequest
from souwen.source_registry import SourceMeta

router = APIRouter()


def _catalog_fields(meta: SourceMeta) -> dict[str, Any]:
    return {
        "auth_requirement": meta.auth_requirement,
        "key_requirement": meta.key_requirement,
        "credential_fields": list(meta.credential_fields),
        "optional_credential_effect": meta.optional_credential_effect,
        "risk_level": meta.risk_level,
        "risk_reasons": sorted(meta.risk_reasons),
        "distribution": meta.distribution,
        "package_extra": meta.package_extra,
        "stability": meta.stability,
        "usage_note": meta.usage_note,
        "default_enabled": meta.default_enabled,
    }


@router.get("/sources/config")
async def get_sources_config():
    """查看所有数据源的频道配置 — 包含启用状态、API Key（仅指示）、代理等。"""
    from souwen.config import get_config
    from souwen.source_registry import (
        get_all_sources,
        has_configured_credentials,
        has_required_credentials,
    )

    cfg = get_config()
    all_sources = get_all_sources()
    result: dict = {}
    for name, meta in all_sources.items():
        sc = cfg.get_source_config(name)
        entry: dict = {
            "enabled": sc.enabled,
            "proxy": sc.proxy,
            "http_backend": sc.http_backend,
            "base_url": sc.base_url,
            "has_api_key": has_configured_credentials(cfg, name, meta),
            "credentials_satisfied": has_required_credentials(cfg, name, meta),
            "headers": sc.headers,
            "params": sc.params,
            "category": meta.category,
            "integration_type": meta.integration_type,
            "description": meta.description,
            **_catalog_fields(meta),
        }
        result[name] = entry
    return result


@router.get("/sources/config/{source_name}")
async def get_source_config(source_name: str):
    """查看单个数据源的频道配置。"""
    from souwen.config import get_config
    from souwen.source_registry import (
        get_source,
        has_configured_credentials,
        has_required_credentials,
    )

    meta = get_source(source_name)
    if meta is None:
        raise HTTPException(404, f"未知数据源: {source_name}")

    cfg = get_config()
    sc = cfg.get_source_config(source_name)
    return {
        "name": source_name,
        "enabled": sc.enabled,
        "proxy": sc.proxy,
        "http_backend": sc.http_backend,
        "base_url": sc.base_url,
        "has_api_key": has_configured_credentials(cfg, source_name, meta),
        "credentials_satisfied": has_required_credentials(cfg, source_name, meta),
        "headers": sc.headers,
        "params": sc.params,
        "category": meta.category,
        "integration_type": meta.integration_type,
        "description": meta.description,
        **_catalog_fields(meta),
    }


@router.put("/sources/config/{source_name}")
async def update_source_config(
    source_name: str,
    req: UpdateSourceConfigRequest,
):
    """更新单个数据源的频道配置（运行时生效）。"""
    from souwen.config import SourceChannelConfig, _validate_proxy_url, get_config
    from souwen.source_registry import is_known_source

    if not is_known_source(source_name):
        raise HTTPException(404, f"未知数据源: {source_name}")

    _VALID_BACKENDS = {"auto", "curl_cffi", "httpx"}
    if req.http_backend is not None and req.http_backend not in _VALID_BACKENDS:
        raise HTTPException(400, f"无效的 http_backend: {req.http_backend}")

    cfg = get_config()
    sc = cfg.sources.get(source_name, SourceChannelConfig())

    if req.enabled is not None:
        sc.enabled = req.enabled
    if req.proxy is not None:
        _PROXY_KEYWORDS = {"inherit", "none", "warp"}
        if req.proxy.strip().lower() not in _PROXY_KEYWORDS and req.proxy.strip():
            try:
                _validate_proxy_url(req.proxy)
            except ValueError as e:
                raise HTTPException(422, f"代理 URL 无效: {e}")
        sc.proxy = req.proxy
    if req.http_backend is not None:
        sc.http_backend = req.http_backend
    if req.base_url is not None:
        if req.base_url:
            _parsed = urlparse(req.base_url)
            if _parsed.scheme not in ("http", "https") or not _parsed.hostname:
                raise HTTPException(
                    status_code=422, detail=f"base_url 必须为 http/https URL: {req.base_url}"
                )
        sc.base_url = req.base_url if req.base_url else None
    if req.api_key is not None:
        sc.api_key = req.api_key if req.api_key else None

    cfg.sources[source_name] = sc
    return {"status": "ok", "source": source_name}
