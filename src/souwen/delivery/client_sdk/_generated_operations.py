"""Generated from contracts/openapi/souwen-openapi-2.0.0rc2.json; do not edit."""

# generator_version=1
# openapi_sha256=e4343a549c99596244c5f7cf8bed0d1675641bb4eec1a44abbcc65f8f6f18de9

from __future__ import annotations

from typing import NamedTuple

SDK_VERSION = "2.0.0rc2"
SUPPORTED_API_MAJOR = 2
OPENAPI_SHA256 = "e4343a549c99596244c5f7cf8bed0d1675641bb4eec1a44abbcc65f8f6f18de9"


class Operation(NamedTuple):
    method: str
    path: str
    request_model: str | None
    response_model: str
    response_statuses: tuple[int, ...]


FETCH = Operation("POST", "/api/v1/fetch", "FetchRequest", "FetchBatch", (200,))
LLM_SEARCH = Operation("POST", "/api/v1/llm-search", "LLMSearchRequest", "LLMSearchResult", (200,))
LIST_PROVIDERS = Operation("GET", "/api/v1/providers", None, "ProviderCatalog", (200,))
SEARCH = Operation("POST", "/api/v1/search", "SearchRequest", "SearchPage", (200,))
HEALTH_LEGACY_ALIAS = Operation("GET", "/health", None, "ProbeResponse", (200,))
HEALTHZ = Operation("GET", "/healthz", None, "ProbeResponse", (200,))
READINESS_LEGACY_ALIAS = Operation("GET", "/readiness", None, "ProbeResponse", (200, 503))
READYZ = Operation("GET", "/readyz", None, "ProbeResponse", (200, 503))

OPERATIONS = {
    "fetch": FETCH,
    "llmSearch": LLM_SEARCH,
    "listProviders": LIST_PROVIDERS,
    "search": SEARCH,
    "healthLegacyAlias": HEALTH_LEGACY_ALIAS,
    "healthz": HEALTHZ,
    "readinessLegacyAlias": READINESS_LEGACY_ALIAS,
    "readyz": READYZ,
}


__all__ = [
    "FETCH",
    "HEALTHZ",
    "HEALTH_LEGACY_ALIAS",
    "LIST_PROVIDERS",
    "LLM_SEARCH",
    "OPENAPI_SHA256",
    "OPERATIONS",
    "Operation",
    "READINESS_LEGACY_ALIAS",
    "READYZ",
    "SDK_VERSION",
    "SEARCH",
    "SUPPORTED_API_MAJOR",
]
