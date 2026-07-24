"""OpenAPI normalization for rollout-gated target operations."""

from __future__ import annotations

from typing import Any

from .rollout import RolloutMode


_TARGET_METHODS = {
    "/api/v1/search": "post",
    "/api/v1/llm-search": "post",
    "/api/v1/fetch": "post",
    "/api/v1/providers": "get",
}
_PROBE_METHODS = {
    "/health": "get",
    "/healthz": "get",
    "/readiness": "get",
    "/readyz": "get",
}
_COMMON_RESPONSE_HEADERS = (
    "X-SouWen-API-Major",
    "X-Request-ID",
    "X-SouWen-Rollout-Mode",
)
_RATE_LIMIT_HEADERS = (
    "Retry-After",
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
)


def _header_components() -> dict[str, dict[str, Any]]:
    return {
        "X-SouWen-API-Major": {"required": True, "schema": {"const": "2"}},
        "X-Request-ID": {"required": True, "schema": {"type": "string"}},
        "X-SouWen-Rollout-Mode": {
            "required": True,
            "schema": {"enum": ["legacy", "target"]},
        },
        "Retry-After": {"required": True, "schema": {"type": "string"}},
        "X-RateLimit-Limit": {"required": True, "schema": {"type": "string"}},
        "X-RateLimit-Remaining": {"required": True, "schema": {"type": "string"}},
        "X-RateLimit-Reset": {"required": True, "schema": {"type": "string"}},
    }


def _add_response_headers(operation: dict[str, Any]) -> None:
    responses = operation.setdefault("responses", {})
    for status, response in responses.items():
        if not isinstance(response, dict):
            continue
        headers = response.setdefault("headers", {})
        for name in _COMMON_RESPONSE_HEADERS:
            headers.setdefault(name, {"$ref": f"#/components/headers/{name}"})
        if status == "429":
            for name in _RATE_LIMIT_HEADERS:
                headers.setdefault(name, {"$ref": f"#/components/headers/{name}"})


def normalize_target_openapi(schema: dict[str, Any], mode: RolloutMode) -> dict[str, Any]:
    schema["x-souwen-api-major"] = 2
    schema["x-souwen-rollout-mode"] = mode.value
    schema["x-souwen-contract-stage"] = "target_runtime_rollout_gated"
    components = schema.setdefault("components", {})
    components.setdefault("headers", {}).update(_header_components())
    if mode is RolloutMode.TARGET:
        components.setdefault("securitySchemes", {}).setdefault(
            "UserToken",
            {"type": "http", "scheme": "bearer"},
        )
    operations = dict(_PROBE_METHODS)
    if mode is RolloutMode.TARGET:
        operations.update(_TARGET_METHODS)
    for path, method in operations.items():
        operation = schema.get("paths", {}).get(path, {}).get(method)
        if not isinstance(operation, dict):
            continue
        _add_response_headers(operation)
        if path in _TARGET_METHODS:
            operation["security"] = [{"UserToken": []}]
        else:
            operation["security"] = []
        responses = operation.setdefault("responses", {})
        if path in _TARGET_METHODS:
            responses.pop("422", None)
            responses.setdefault("400", {"description": "Invalid target request"})
        if path == "/health":
            operation["x-souwen-alias-of"] = "/healthz"
        elif path == "/readiness":
            operation["x-souwen-alias-of"] = "/readyz"
    return schema


__all__ = ["normalize_target_openapi"]
