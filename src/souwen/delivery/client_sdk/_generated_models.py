"""Generated from contracts/openapi/souwen-openapi-2.0.0rc2.json; do not edit."""

# generator_version=1
# openapi_sha256=e4343a549c99596244c5f7cf8bed0d1675641bb4eec1a44abbcc65f8f6f18de9

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class _OpenModel(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, hide_input_in_errors=True)


class ClientRequestContext(_StrictModel):
    "Client-supplied correlation subset without server-owned API state."

    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)


class ContentMetadata(_StrictModel):
    "Safe normalized-content metadata for one Fetch result."

    charset: str | None = Field(default=None, min_length=1, max_length=64)
    content_length: int | None = Field(default=None, ge=0.0)
    media_type: str = Field(min_length=1, max_length=128)
    quality: Literal["high", "low"] | None = None
    retrieved_at: datetime | None = None
    truncated: bool


class ErrorDetail(_StrictModel):
    "Public error details with no upstream payload or diagnostic fields."

    code: Literal[
        "invalid_request",
        "unauthenticated",
        "forbidden",
        "not_found",
        "conflict",
        "api_major_mismatch",
        "rate_limited",
        "payload_too_large",
        "unsupported_media_type",
        "worker_unavailable",
        "worker_not_ready",
        "worker_overloaded",
        "worker_timeout",
        "worker_protocol_mismatch",
        "provider_timeout",
        "provider_unavailable",
        "policy_blocked",
        "internal_error",
    ]
    message: str = Field(min_length=1, max_length=512)
    provider: str | None = Field(default=None, min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    retryable: bool


class ErrorResponse(_StrictModel):
    "Target External Data API error envelope."

    context: RequestContext
    error: ErrorDetail


class EvidenceItem(_StrictModel):
    "Verifiable public evidence attached to an LLM Search item."

    id: str = Field(min_length=1, max_length=512)
    item_id: str = Field(min_length=1, max_length=512)
    provider: str = Field(min_length=1, max_length=128)
    public_url: AnyUrl = Field(min_length=1)
    retrieved_at: datetime
    title_or_snippet: str = Field(min_length=1, max_length=20000)


class FetchBatch(_StrictModel):
    "Canonical Fetch batch emitted by a Fetch provider or Core module."

    context: RequestContext
    items: list[FetchResult]
    meta: FetchMeta


class FetchContentOptions(_StrictModel):
    "Bounded normalized-content extraction options."

    max_code_points: int | None = Field(default=None, ge=1.0, le=1000000.0)


class FetchMeta(_StrictModel):
    "Batch-level Fetch outcome summary."

    partial: bool = False


class FetchPolicyOptions(_StrictModel):
    "Policy options that cannot disable server-side Fetch protections."

    respect_robots: Literal[True] | None = None


class FetchRequest(_StrictModel):
    "Canonical Fetch input; target validation does not replace SSRF controls."

    content: FetchContentOptions | None = None
    policy: FetchPolicyOptions | None = None
    providers: list[ProviderRef] | None = None
    strategy: Literal["fallback", "fanout"] | None = None
    targets: list[AnyUrl] = Field(min_length=1, max_length=20)


class FetchResult(_StrictModel):
    "One per-target Fetch outcome, including its own provenance or safe error."

    content: str | None = Field(default=None, max_length=1000000)
    content_metadata: ContentMetadata | None = None
    error: ErrorDetail | None = None
    final_url: AnyUrl | None = Field(default=None, min_length=1)
    provenance: list[Provenance] = Field(min_length=1)
    status: Literal["success", "failed", "blocked"]
    target: AnyUrl = Field(min_length=1)
    title: str | None = Field(default=None, max_length=2048)


class HTTPValidationError(_OpenModel):
    detail: list[ValidationError] | None = None


class LLMFetchOptions(_StrictModel):
    "Bounded request to enable a separately secured downstream Fetch step."

    enabled: bool = True


class LLMSearchBudget(_StrictModel):
    "Execution limits, not a billing promise."

    max_attempts: int | None = Field(default=None, ge=1.0)
    timeout_seconds: float | None = Field(default=None, le=120.0, gt=0.0)


class LLMSearchRequest(_StrictModel):
    "Canonical single-operation LLM Search input."

    budget: LLMSearchBudget | None = None
    fetch: LLMFetchOptions | None = None
    max_results_per_provider: int | None = Field(default=None, ge=1.0)
    providers: list[ProviderRef] = Field(min_length=1)
    query: str = Field(min_length=1, max_length=4096)
    strategy: Literal["single", "fanout", "first_success"]
    synthesis_profile: str | None = Field(default=None, min_length=1, max_length=128)


class LLMSearchResult(_StrictModel):
    "Canonical LLM Search result with evidence and always-present usage."

    answer: str | None = Field(default=None, max_length=100000)
    context: RequestContext
    evidence: list[EvidenceItem]
    items: list[SearchItem]
    meta: SearchMeta
    query: str = Field(min_length=1, max_length=4096)
    usage: Usage


class PageInfo(_StrictModel):
    "Opaque continuation information for a canonical page."

    limit: int = Field(ge=1.0, le=100.0)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=2048)
    total: int | None = Field(default=None, ge=0.0)


class ProbeResponse(_StrictModel):
    "Superset payload shared by canonical probes and their 2.x aliases."

    components: (
        dict[str, Literal["ready", "not_ready", "optional_unavailable", "disabled"]] | None
    ) = None
    config_revision: str | None = Field(default=None, min_length=1, max_length=128)
    context: RequestContext
    error: str | None = Field(default=None, min_length=1, max_length=256)
    ready: bool
    rollout_mode: RolloutMode
    source_sha: str | None = Field(default=None, min_length=40, max_length=40)
    status: Literal["ok", "ready", "not_ready"]
    version: str = Field(min_length=1, max_length=64)
    worker_source_sha: str | None = Field(default=None, min_length=40, max_length=40)
    wrapper_sha: str | None = Field(default=None, min_length=40, max_length=40)


class Provenance(_StrictModel):
    "Safe public provenance for one canonical result."

    attempt: int | None = Field(default=None, ge=1.0)
    outcome: Literal["success", "empty", "failed"]
    provider: str = Field(min_length=1, max_length=128)
    retrieved_at: datetime | None = None


class ProviderCatalog(_StrictModel):
    "Migrated Provider v2 catalog without legacy source or config readback fields."

    context: RequestContext
    items: list[ProviderCatalogItem]


class ProviderCatalogItem(_StrictModel):
    "Safe Provider v2 availability without config or secret values."

    availability: Literal["available", "unavailable"]
    capabilities: list[Literal["search", "llm_search", "fetch"]] = Field(min_length=1)
    missing_fields: list[str] = Field(default_factory=list)
    provenance: list[Provenance] = Field(min_length=1)
    provider: str = Field(min_length=1, max_length=128)
    reason: Literal["available", "disabled", "missing_configuration", "not_eligible"]


class ProviderFailure(_StrictModel):
    "A machine-readable provider failure retained in partial results."

    code: Literal[
        "invalid_request",
        "unauthenticated",
        "forbidden",
        "not_found",
        "conflict",
        "api_major_mismatch",
        "rate_limited",
        "payload_too_large",
        "unsupported_media_type",
        "worker_unavailable",
        "worker_not_ready",
        "worker_overloaded",
        "worker_timeout",
        "worker_protocol_mismatch",
        "provider_timeout",
        "provider_unavailable",
        "policy_blocked",
        "internal_error",
    ]
    provider: str = Field(min_length=1, max_length=128)


class ProviderRef(_StrictModel):
    "A public, stable provider identity; never a model, URL, or secret reference."

    display_name: str | None = Field(default=None, min_length=1, max_length=256)
    id: str = Field(min_length=1, max_length=128, pattern="^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    kind: Literal["search", "llm_search", "fetch"]


class RequestContext(_StrictModel):
    "Correlation data carried by every canonical response."

    api_major: Literal[2] = 2
    request_id: str = Field(min_length=1, max_length=128)
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)


RolloutMode = Literal["legacy", "target"]


class SearchAttributes(_StrictModel):
    "Explicit additive metadata shared by the first Provider v2 slices."

    authors: list[str] = Field(default_factory=list)
    citation_count: int | None = Field(default=None, ge=0.0)
    identifiers: list[SearchIdentifier] = Field(default_factory=list)
    language: str | None = Field(default=None, min_length=2, max_length=35)
    open_access: bool | None = None
    resource_type: str | None = Field(default=None, min_length=1, max_length=64)
    year: int | None = Field(default=None, ge=0.0, le=9999.0)


class SearchFilters(_StrictModel):
    "Schema-listed filters for the initial canonical Search surface."

    language: str | None = Field(default=None, min_length=2, max_length=35)
    open_access: bool | None = None
    resource_type: str | None = Field(default=None, min_length=1, max_length=64)
    year_from: int | None = Field(default=None, ge=0.0, le=9999.0)
    year_to: int | None = Field(default=None, ge=0.0, le=9999.0)


class SearchIdentifier(_StrictModel):
    "A stable domain identifier such as DOI or OpenAlex ID."

    scheme: str = Field(min_length=1, max_length=32, pattern="^[a-z][a-z0-9_.-]*$")
    value: str = Field(min_length=1, max_length=512)


class SearchItem(_StrictModel):
    "One normalized Search result without provider-private payloads."

    attributes: SearchAttributes | None = None
    id: str = Field(min_length=1, max_length=512)
    provenance: list[Provenance] = Field(min_length=1)
    rank: int | None = Field(default=None, ge=1.0)
    snippet: str | None = Field(default=None, max_length=20000)
    title: str = Field(min_length=1, max_length=2048)
    url: AnyUrl | None = Field(default=None, min_length=1)


class SearchMeta(_StrictModel):
    "Provider outcome summary for Search and LLM Search results."

    failed: list[ProviderFailure] = Field(default_factory=list)
    partial: bool = False
    requested: list[str] = Field(default_factory=list)
    succeeded: list[str] = Field(default_factory=list)


class SearchPage(_StrictModel):
    "Canonical Search page emitted by a Search provider or Core module."

    context: RequestContext
    items: list[SearchItem]
    meta: SearchMeta
    page: PageInfo


class SearchPageRequest(_StrictModel):
    "Client paging input; the cursor remains opaque to the client."

    cursor: str | None = Field(default=None, min_length=1, max_length=2048)
    limit: int = Field(ge=1.0, le=100.0)


class SearchRequest(_StrictModel):
    "Canonical Search use-case input."

    domains: list[
        Literal[
            "paper",
            "book",
            "research_output",
            "patent",
            "web",
            "news",
            "images",
            "videos",
            "social",
            "office",
            "developer",
            "cn_tech",
            "knowledge",
        ]
    ] = Field(min_length=1)
    filters: SearchFilters | None = None
    page: SearchPageRequest | None = None
    providers: list[ProviderRef] | None = None
    query: str = Field(min_length=1, max_length=4096)
    request_context: ClientRequestContext | None = None


class Usage(_StrictModel):
    "Provider-reported usage only; unknown values are represented by ``None``."

    cost: float | None = Field(default=None, ge=0.0)
    currency: str | None = Field(default=None, min_length=1, max_length=16)
    input_tokens: int | None = Field(default=None, ge=0.0)
    output_tokens: int | None = Field(default=None, ge=0.0)


class ValidationError(_OpenModel):
    ctx: dict[str, Any] | None = None
    input: Any | None = None
    loc: list[str | int]
    msg: str
    type: str


ClientRequestContext.model_rebuild()
ContentMetadata.model_rebuild()
ErrorDetail.model_rebuild()
ErrorResponse.model_rebuild()
EvidenceItem.model_rebuild()
FetchBatch.model_rebuild()
FetchContentOptions.model_rebuild()
FetchMeta.model_rebuild()
FetchPolicyOptions.model_rebuild()
FetchRequest.model_rebuild()
FetchResult.model_rebuild()
HTTPValidationError.model_rebuild()
LLMFetchOptions.model_rebuild()
LLMSearchBudget.model_rebuild()
LLMSearchRequest.model_rebuild()
LLMSearchResult.model_rebuild()
PageInfo.model_rebuild()
ProbeResponse.model_rebuild()
Provenance.model_rebuild()
ProviderCatalog.model_rebuild()
ProviderCatalogItem.model_rebuild()
ProviderFailure.model_rebuild()
ProviderRef.model_rebuild()
RequestContext.model_rebuild()
SearchAttributes.model_rebuild()
SearchFilters.model_rebuild()
SearchIdentifier.model_rebuild()
SearchItem.model_rebuild()
SearchMeta.model_rebuild()
SearchPage.model_rebuild()
SearchPageRequest.model_rebuild()
SearchRequest.model_rebuild()
Usage.model_rebuild()
ValidationError.model_rebuild()


__all__ = [
    "ClientRequestContext",
    "ContentMetadata",
    "ErrorDetail",
    "ErrorResponse",
    "EvidenceItem",
    "FetchBatch",
    "FetchContentOptions",
    "FetchMeta",
    "FetchPolicyOptions",
    "FetchRequest",
    "FetchResult",
    "HTTPValidationError",
    "LLMFetchOptions",
    "LLMSearchBudget",
    "LLMSearchRequest",
    "LLMSearchResult",
    "PageInfo",
    "ProbeResponse",
    "Provenance",
    "ProviderCatalog",
    "ProviderCatalogItem",
    "ProviderFailure",
    "ProviderRef",
    "RequestContext",
    "RolloutMode",
    "SearchAttributes",
    "SearchFilters",
    "SearchIdentifier",
    "SearchItem",
    "SearchMeta",
    "SearchPage",
    "SearchPageRequest",
    "SearchRequest",
    "Usage",
    "ValidationError",
]
