"""Deterministic target-only OpenAPI materialization and semantic comparison."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import lru_cache
from typing import Any

from souwen import __version__

from .app import create_target_delivery_app
from .rollout import RolloutMode
from .router import ReadinessSnapshot, RuntimeMetadata, TargetDeliveryServices


TARGET_OPENAPI_VERSION = __version__
TARGET_OPENAPI_PATHS = frozenset(
    {
        "/api/v1/search",
        "/api/v1/llm-search",
        "/api/v1/fetch",
        "/api/v1/providers",
        "/health",
        "/healthz",
        "/readiness",
        "/readyz",
    }
)
_HTTP_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put", "trace"})


class _SchemaOnlyService:
    async def search(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("schema-only service cannot execute requests")

    async def fetch(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("schema-only service cannot execute requests")


def _schema_only_services() -> TargetDeliveryServices:
    service = _SchemaOnlyService()
    return TargetDeliveryServices(
        search=service,  # type: ignore[arg-type]
        llm_search=service,  # type: ignore[arg-type]
        fetch=service,  # type: ignore[arg-type]
        provider_items=(),
        readiness=lambda: ReadinessSnapshot(ready=True, components={"api": "ready"}),
    )


@lru_cache(maxsize=None)
def _materialize_target_openapi(version: str) -> dict[str, Any]:
    app = create_target_delivery_app(
        _schema_only_services(),
        RuntimeMetadata(
            version=version,
            source_sha=None,
            rollout_mode=RolloutMode.TARGET,
        ),
        require_user=lambda: None,
        rate_limit=lambda: None,
    )
    document = app.openapi()
    if set(document.get("paths", {})) != TARGET_OPENAPI_PATHS:
        raise RuntimeError("target OpenAPI materializer produced a non-canonical path set")
    return document


def build_target_openapi_document(version: str = TARGET_OPENAPI_VERSION) -> dict[str, Any]:
    """Build a target-only document without config, network, secrets, or runtime state."""

    return deepcopy(_materialize_target_openapi(version))


def canonical_openapi_bytes(document: dict[str, Any] | None = None) -> bytes:
    """Serialize an OpenAPI document using the release checksum byte contract."""

    materialized = build_target_openapi_document() if document is None else document
    return json.dumps(
        materialized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_openapi_sha256(document: dict[str, Any] | None = None) -> str:
    return hashlib.sha256(canonical_openapi_bytes(document)).hexdigest()


def _operations(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    operations: dict[str, dict[str, Any]] = {}
    for path, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        path_contract = {key: value for key, value in path_item.items() if key not in _HTTP_METHODS}
        for method, operation in path_item.items():
            if method in _HTTP_METHODS and isinstance(operation, dict):
                operations[f"{method.upper()} {path}"] = {
                    "operation": operation,
                    "path_contract": path_contract,
                }
    return operations


def _named_components(document: dict[str, Any], component: str) -> dict[str, Any]:
    components = document.get("components", {})
    if not isinstance(components, dict):
        return {}
    values = components.get(component, {})
    return values if isinstance(values, dict) else {}


def _component_sections(document: dict[str, Any]) -> dict[str, Any]:
    components = document.get("components", {})
    return components if isinstance(components, dict) else {}


def _changed_keys(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(key for key in before.keys() & after.keys() if before[key] != after[key])


def semantic_diff_openapi(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Return a deterministic, conservative semantic compatibility report."""

    before_operations = _operations(baseline)
    after_operations = _operations(candidate)
    before_schemas = _named_components(baseline, "schemas")
    after_schemas = _named_components(candidate, "schemas")

    metadata_fields = (
        "openapi",
        "info",
        "security",
        "servers",
        "x-souwen-api-major",
        "x-souwen-contract-stage",
        "x-souwen-rollout-mode",
    )
    metadata_changes = [
        field for field in metadata_fields if baseline.get(field) != candidate.get(field)
    ]
    baseline_components = _component_sections(baseline)
    candidate_components = _component_sections(candidate)
    component_sections = (baseline_components.keys() | candidate_components.keys()) - {"schemas"}
    metadata_changes.extend(
        f"components.{section}"
        for section in sorted(component_sections)
        if baseline_components.get(section) != candidate_components.get(section)
    )

    report: dict[str, Any] = {
        "added_operations": sorted(after_operations.keys() - before_operations.keys()),
        "removed_operations": sorted(before_operations.keys() - after_operations.keys()),
        "changed_operations": _changed_keys(before_operations, after_operations),
        "added_schemas": sorted(after_schemas.keys() - before_schemas.keys()),
        "removed_schemas": sorted(before_schemas.keys() - after_schemas.keys()),
        "changed_schemas": _changed_keys(before_schemas, after_schemas),
        "metadata_changes": sorted(metadata_changes),
    }
    report["breaking"] = any(
        report[key]
        for key in (
            "removed_operations",
            "changed_operations",
            "removed_schemas",
            "changed_schemas",
            "metadata_changes",
        )
    )
    return report


__all__ = [
    "TARGET_OPENAPI_PATHS",
    "TARGET_OPENAPI_VERSION",
    "build_target_openapi_document",
    "canonical_openapi_bytes",
    "canonical_openapi_sha256",
    "semantic_diff_openapi",
]
