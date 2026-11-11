"""Generated from contracts/openapi/souwen-openapi-2.0.0rc6.json; do not edit."""

# generator_version=1
# openapi_sha256=b11642a641558401f1cb6790af41e331da75add0efbd6494606db0a011e53509

from __future__ import annotations

from typing import NamedTuple

SDK_VERSION = "2.0.0rc6"
SUPPORTED_API_MAJOR = 2
OPENAPI_SHA256 = "b11642a641558401f1cb6790af41e331da75add0efbd6494606db0a011e53509"


class Operation(NamedTuple):
    method: str
    path: str
    request_model: str | None
    response_model: str
    response_statuses: tuple[int, ...]


FETCH = Operation("POST", "/api/v1/fetch", "FetchRequest", "FetchBatch", (200,))
LIST_PROVIDERS = Operation("GET", "/api/v1/providers", None, "ProviderCatalog", (200,))
SEARCH = Operation("POST", "/api/v1/search", "SearchRequest", "SearchPage", (200,))
HEALTH_ALIAS = Operation("GET", "/health", None, "ProbeResponse", (200,))
HEALTHZ = Operation("GET", "/healthz", None, "ProbeResponse", (200,))
READINESS_ALIAS = Operation("GET", "/readiness", None, "ProbeResponse", (200, 503))
READYZ = Operation("GET", "/readyz", None, "ProbeResponse", (200, 503))

OPERATIONS = {
    "fetch": FETCH,
    "listProviders": LIST_PROVIDERS,
    "search": SEARCH,
    "healthAlias": HEALTH_ALIAS,
    "healthz": HEALTHZ,
    "readinessAlias": READINESS_ALIAS,
    "readyz": READYZ,
}


__all__ = [
    "FETCH",
    "HEALTHZ",
    "HEALTH_ALIAS",
    "LIST_PROVIDERS",
    "OPENAPI_SHA256",
    "OPERATIONS",
    "Operation",
    "READINESS_ALIAS",
    "READYZ",
    "SDK_VERSION",
    "SEARCH",
    "SUPPORTED_API_MAJOR",
]
