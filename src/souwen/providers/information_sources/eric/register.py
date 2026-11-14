"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.common_runtime.transport import HttpTransport
from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.paper.eric import EricClient

from .adapter import EricSearchProvider
from .manifest import ERIC_PROVIDER_MANIFEST
from .spec import ERIC_REST_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del reviewed_proxy  # REST 固定端点，无通道覆盖
    from souwen.platform.provider_spec import resolve_provider_inputs
    from souwen.platform.provider_spec.validation import validate_spec_manifest

    validate_spec_manifest(ERIC_REST_SPEC, ERIC_PROVIDER_MANIFEST)
    resolved_configuration, resolved_secrets = resolve_provider_inputs(
        ERIC_REST_SPEC, configuration, secrets
    )
    headers = {"User-Agent": "SouWen/3.0.0a1"}
    transport = HttpTransport(
        base_url=ERIC_REST_SPEC.base_url,
        headers=headers,
        timeout=resolved_configuration["timeout_seconds"],
        max_retries=resolved_configuration["max_retries"],
        proxy=None,
        follow_redirects=False,
    )
    return EricSearchProvider(
        EricClient(transport=transport), enabled=resolved_configuration["enabled"]
    )


def resolve_configuration(config: SouWenConfig) -> dict[str, object]:
    if not config.is_source_enabled("eric", default=True):
        raise ValueError("provider is disabled")
    source = config.get_source_config("eric")
    from datetime import timedelta

    timeout = source.timeout or config.timeout
    max_retries = config.max_retries
    _ = timedelta  # noqa: F841 — 语义占位（spec 配置校验在 spec 层完成）
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 0 < timeout <= 120
        or not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or not 0 <= max_retries <= 10
    ):
        raise ValueError("invalid ERIC transport configuration")
    return {"enabled": True, "max_retries": max_retries, "timeout_seconds": timeout}


MANIFEST = ERIC_PROVIDER_MANIFEST
SPEC = ERIC_REST_SPEC
PROVIDER_TYPE = EricSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider", "resolve_configuration"]
