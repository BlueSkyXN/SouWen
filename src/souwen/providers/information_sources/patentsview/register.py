"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.common_runtime.transport import HttpTransport  # noqa: F401 — 测试桩按模块属性替换
from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.patent.patentsview import PatentsViewClient

from .adapter import PatentsViewSearchProvider
from .manifest import PATENTSVIEW_PROVIDER_MANIFEST
from .spec import PATENTSVIEW_REST_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del reviewed_proxy  # REST 固定端点，无通道覆盖
    from souwen.platform.provider_spec import resolve_provider_inputs
    from souwen.platform.provider_spec.validation import validate_spec_manifest

    validate_spec_manifest(PATENTSVIEW_REST_SPEC, PATENTSVIEW_PROVIDER_MANIFEST)
    resolved_configuration, resolved_secrets = resolve_provider_inputs(
        PATENTSVIEW_REST_SPEC, configuration, secrets
    )
    headers = {"User-Agent": "SouWen/3.0.0a1"}
    reference = PATENTSVIEW_REST_SPEC.auth.reference
    if reference is not None:
        value = resolved_secrets.get(reference)
        if value is not None:
            headers[PATENTSVIEW_REST_SPEC.auth.field_name] = value
    transport = HttpTransport(
        base_url=PATENTSVIEW_REST_SPEC.base_url,
        headers=headers,
        timeout=resolved_configuration["timeout_seconds"],
        max_retries=resolved_configuration["max_retries"],
        proxy=None,
        follow_redirects=False,
    )
    return PatentsViewSearchProvider(
        PatentsViewClient(transport=transport), enabled=resolved_configuration["enabled"]
    )


def resolve_configuration(config: SouWenConfig) -> dict[str, object]:
    if not config.is_source_enabled("patentsview", default=False):
        raise ValueError("provider is disabled")
    source = config.get_source_config("patentsview")
    timeout = source.timeout or config.timeout
    max_retries = config.max_retries
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 0 < timeout <= 120
        or not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or not 0 <= max_retries <= 10
    ):
        raise ValueError("invalid PatentsView transport configuration")
    return {"enabled": True, "max_retries": max_retries, "timeout_seconds": timeout}


MANIFEST = PATENTSVIEW_PROVIDER_MANIFEST
SPEC = PATENTSVIEW_REST_SPEC
PROVIDER_TYPE = PatentsViewSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider", "resolve_configuration"]
