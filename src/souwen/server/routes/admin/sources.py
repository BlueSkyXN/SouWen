"""数据源频道配置 — /admin/sources/config[/{name}]"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from souwen.config.models import LLM_SEARCH_IDENTITY_PARAMS
from souwen.registry.meta import (
    SourceMeta,
    is_llm_search_gateway_requirement,
    source_config_validation_reason,
)
from souwen.server.routes._common import (
    normalize_required_query_arg,
    redact_secret_mapping,
    redact_secret_text,
    redact_secret_url,
    reject_redacted_placeholder,
)
from souwen.server.schemas import (
    SourceChannelConfigResponse,
    UpdateSourceConfigRequest,
    UpdateSourceConfigResponse,
)

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
        "default_for": sorted(meta.default_for),
    }


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip()


def _safe_source_url(value: str | None) -> str | None:
    return redact_secret_url(value) if value else value


def _source_edition_fields(source_name: str, edition: str) -> dict[str, Any]:
    from souwen.editions import source_policy
    from souwen.registry import get as get_adapter

    adapter = get_adapter(source_name)
    if adapter is None:  # pragma: no cover - SourceMeta/catalog 与 registry 同源，防御漂移
        raise KeyError(f"missing registry adapter for source {source_name!r}")
    policy = source_policy(adapter, edition)
    return {
        "min_edition": policy.min_edition,
        "edition_available": policy.available,
        "edition_reason": policy.reason,
    }


def _source_config_payload(
    *,
    source_name: str,
    include_name: bool = False,
    sc: Any,
    meta: SourceMeta,
    catalog_entry: Any,
    configured_credentials: bool,
    credentials_satisfied: bool,
    missing_fields: list[str],
    config_reason: str,
    enabled: bool,
    available: bool,
    edition_fields: dict[str, Any],
) -> dict[str, Any]:
    hides_gateway_values = any(
        is_llm_search_gateway_requirement(item) for item in meta.credential_fields
    )
    safe_params = redact_secret_mapping(sc.params)
    if hides_gateway_values:
        for field in LLM_SEARCH_IDENTITY_PARAMS.intersection(safe_params):
            safe_params[field] = "***"
    payload: dict[str, Any] = {
        "enabled": enabled,
        "proxy": _safe_source_url(sc.proxy),
        "http_backend": sc.http_backend,
        "base_url": None if hides_gateway_values else _safe_source_url(sc.base_url),
        "timeout": sc.timeout,
        "has_api_key": configured_credentials,
        "configured_credentials": configured_credentials,
        "credentials_satisfied": credentials_satisfied,
        "missing_credential_fields": missing_fields,
        "config_valid": not config_reason,
        "config_reason": config_reason,
        "available": available,
        "headers": redact_secret_mapping(sc.headers),
        "params": safe_params,
        "category": meta.category,
        "domain": catalog_entry.domain,
        "capabilities": list(catalog_entry.capabilities),
        "integration_type": meta.integration_type,
        "description": meta.description,
        **edition_fields,
        **_catalog_fields(meta),
    }
    if include_name:
        payload["name"] = source_name
    return payload


@router.get("/sources/config", response_model=dict[str, SourceChannelConfigResponse])
async def get_sources_config():
    """查看所有数据源的频道配置 — 包含启用状态、API Key（仅指示）、代理等。"""
    from souwen.config import get_config
    from souwen.registry.catalog import source_catalog
    from souwen.registry.meta import (
        get_all_sources,
        has_configured_credentials,
        has_required_credentials,
        missing_credential_fields,
    )

    cfg = get_config()
    all_sources = get_all_sources()
    catalog = source_catalog()
    result: dict = {}
    for name, meta in all_sources.items():
        catalog_entry = catalog[name]
        sc = cfg.get_source_config(name)
        configured_credentials = has_configured_credentials(cfg, name, meta)
        credentials_satisfied = has_required_credentials(cfg, name, meta)
        missing_fields = missing_credential_fields(cfg, name, meta)
        config_reason = source_config_validation_reason(cfg, name, meta)
        edition_fields = _source_edition_fields(name, cfg.edition)
        enabled = cfg.is_source_enabled(name, default=meta.runtime_default_enabled)
        result[name] = _source_config_payload(
            source_name=name,
            sc=sc,
            meta=meta,
            catalog_entry=catalog_entry,
            configured_credentials=configured_credentials,
            credentials_satisfied=credentials_satisfied,
            missing_fields=missing_fields,
            config_reason=config_reason,
            enabled=enabled,
            available=(
                enabled
                and not config_reason
                and credentials_satisfied
                and edition_fields["edition_available"]
            ),
            edition_fields=edition_fields,
        )
    return result


@router.get("/sources/config/{source_name}", response_model=SourceChannelConfigResponse)
async def get_source_config(source_name: str):
    """查看单个数据源的频道配置。"""
    from souwen.config import get_config
    from souwen.registry.catalog import source_catalog
    from souwen.registry.meta import (
        get_source,
        has_configured_credentials,
        has_required_credentials,
        missing_credential_fields,
    )

    source_name = normalize_required_query_arg(source_name, "source_name")
    meta = get_source(source_name)
    if meta is None:
        raise HTTPException(404, f"未知数据源: {source_name}")

    cfg = get_config()
    sc = cfg.get_source_config(source_name)
    catalog_entry = source_catalog()[source_name]
    configured_credentials = has_configured_credentials(cfg, source_name, meta)
    credentials_satisfied = has_required_credentials(cfg, source_name, meta)
    missing_fields = missing_credential_fields(cfg, source_name, meta)
    config_reason = source_config_validation_reason(cfg, source_name, meta)
    edition_fields = _source_edition_fields(source_name, cfg.edition)
    enabled = cfg.is_source_enabled(source_name, default=meta.runtime_default_enabled)
    return _source_config_payload(
        source_name=source_name,
        include_name=True,
        sc=sc,
        meta=meta,
        catalog_entry=catalog_entry,
        configured_credentials=configured_credentials,
        credentials_satisfied=credentials_satisfied,
        missing_fields=missing_fields,
        config_reason=config_reason,
        enabled=enabled,
        available=(
            enabled
            and not config_reason
            and credentials_satisfied
            and edition_fields["edition_available"]
        ),
        edition_fields=edition_fields,
    )


@router.put("/sources/config/{source_name}", response_model=UpdateSourceConfigResponse)
async def update_source_config(
    source_name: str,
    req: UpdateSourceConfigRequest,
):
    """更新单个数据源的频道配置（运行时生效）。"""
    from souwen.config import SourceChannelConfig, _validate_proxy_url, get_config
    from souwen.registry.meta import is_known_source

    source_name = normalize_required_query_arg(source_name, "source_name")
    if not is_known_source(source_name):
        raise HTTPException(404, f"未知数据源: {source_name}")

    _VALID_BACKENDS = {"auto", "curl_cffi", "httpx"}

    cfg = get_config()
    sc = cfg.sources.get(source_name, SourceChannelConfig())

    if req.enabled is not None:
        sc.enabled = req.enabled
    if req.proxy is not None:
        proxy_value = req.proxy.strip()
        reject_redacted_placeholder(proxy_value, "proxy")
        _PROXY_KEYWORDS = {"inherit", "none", "warp"}
        proxy_keyword = proxy_value.lower()
        if proxy_keyword not in _PROXY_KEYWORDS and proxy_value:
            try:
                validated_proxy = _validate_proxy_url(proxy_value)
            except ValueError as e:
                detail = redact_secret_text(str(e)) or "代理 URL 无效"
                raise HTTPException(422, f"代理 URL 无效: {detail}")
            sc.proxy = validated_proxy or "inherit"
        elif proxy_keyword in _PROXY_KEYWORDS:
            sc.proxy = proxy_keyword
        else:
            sc.proxy = "inherit"
    if req.http_backend is not None:
        http_backend = req.http_backend.strip()
        if not http_backend:
            raise HTTPException(422, "http_backend 不能是空字符串")
        if http_backend not in _VALID_BACKENDS:
            raise HTTPException(400, f"无效的 http_backend: {http_backend}")
        sc.http_backend = http_backend
    if req.base_url is not None:
        base_url = _strip_optional(req.base_url)
        reject_redacted_placeholder(base_url, "base_url")
        if base_url:
            _parsed = urlparse(base_url)
            if _parsed.scheme not in ("http", "https") or not _parsed.hostname:
                safe_base_url = redact_secret_url(base_url)
                raise HTTPException(
                    status_code=422,
                    detail=f"base_url 必须为 http/https URL: {safe_base_url}",
                )
        sc.base_url = base_url or None
    if "timeout" in req.model_fields_set:
        sc.timeout = req.timeout
    if req.api_key is not None:
        sc.api_key = req.api_key if req.api_key else None

    cfg.sources[source_name] = sc
    return {"status": "ok", "source": source_name}
