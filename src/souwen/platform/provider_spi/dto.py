"""Canonical provider-facing DTOs for the target External Data API.

These bindings are transport-neutral. They are shared by Core modules and
provider adapters, but do not import concrete providers or delivery frameworks.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Literal, TypeAlias

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class CanonicalModel(BaseModel):
    """Immutable, strict base for target canonical DTOs."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class RequestContext(CanonicalModel):
    """Correlation data carried by every canonical response."""

    request_id: str = Field(min_length=1, max_length=128)
    api_major: Literal[2] = 2
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)


class ProviderRef(CanonicalModel):
    """A public, stable provider identity; never a model, URL, or secret reference."""

    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    kind: Capability
    display_name: str | None = Field(default=None, min_length=1, max_length=256)


class Provenance(CanonicalModel):
    """Safe public provenance for one canonical result."""

    provider: str = Field(min_length=1, max_length=128)
    attempt: int | None = Field(default=None, ge=1)
    outcome: Literal["success", "empty", "failed"]
    retrieved_at: datetime | None = None


ProviderProvenance = Provenance


class PageInfo(CanonicalModel):
    """Opaque continuation information for a canonical page."""

    limit: int = Field(ge=1, le=100)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=2048)
    total: int | None = Field(default=None, ge=0)


class Usage(CanonicalModel):
    """Provider-reported usage only; unknown values are represented by ``None``."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=1, max_length=16)

    @model_validator(mode="after")
    def _cost_and_currency_are_reported_together(self) -> Usage:
        if (self.cost is None) != (self.currency is None):
            raise ValueError("cost and currency must both be present or both be null")
        return self


UsageMetadata = Usage


CanonicalErrorCode: TypeAlias = Literal[
    "invalid_request",
    "unauthenticated",
    "forbidden",
    "not_found",
    "conflict",
    "api_major_mismatch",
    "rate_limited",
    "payload_too_large",
    "unsupported_media_type",
    "provider_timeout",
    "provider_unavailable",
    "policy_blocked",
    "internal_error",
]

Capability: TypeAlias = Literal["search", "llm_search", "fetch"]


class ErrorDetail(CanonicalModel):
    """Public error details with no upstream payload or diagnostic fields."""

    code: CanonicalErrorCode
    message: str = Field(min_length=1, max_length=512)
    retryable: bool
    request_id: str = Field(min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=128)


class ErrorResponse(CanonicalModel):
    """Target External Data API error envelope."""

    error: ErrorDetail
    context: RequestContext

    @model_validator(mode="after")
    def _matches_request_context(self) -> ErrorResponse:
        if self.error.request_id != self.context.request_id:
            raise ValueError("error.request_id must match context.request_id")
        return self


class ProviderProbe(CanonicalModel):
    """Safe bounded result of an explicitly requested provider probe."""

    provider: str = Field(min_length=1, max_length=128)
    capability: Capability
    status: Literal["available", "unavailable"]


SearchDomain: TypeAlias = Literal[
    "paper",
    "book",
    "research_output",
    "patent",
    "web",
    "news",
    "images",
    "videos",
]


class SearchPageRequest(CanonicalModel):
    """Client paging input; the cursor remains opaque to the client."""

    limit: int = Field(ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)


class ClientRequestContext(CanonicalModel):
    """Client-supplied correlation subset without server-owned API state."""

    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)


class SearchFilters(CanonicalModel):
    """Schema-listed filters for the initial canonical Search surface."""

    year_from: int | None = Field(default=None, ge=0, le=9999)
    year_to: int | None = Field(default=None, ge=0, le=9999)
    language: str | None = Field(default=None, min_length=2, max_length=35)
    open_access: bool | None = None
    resource_type: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _year_range_is_ordered(self) -> SearchFilters:
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from must not exceed year_to")
        return self


class SearchRequest(CanonicalModel):
    """Canonical Search use-case input."""

    query: str = Field(min_length=1, max_length=4096)
    domains: tuple[SearchDomain, ...] = Field(min_length=1)
    providers: tuple[ProviderRef, ...] | None = None
    page: SearchPageRequest | None = None
    filters: SearchFilters | None = None
    request_context: ClientRequestContext | None = None

    @field_validator("query")
    @classmethod
    def _normalise_query(cls, value: str) -> str:
        normalised = value.strip()
        if not normalised:
            raise ValueError("query must not be blank")
        return normalised

    @model_validator(mode="after")
    def _unique_provider_ids(self) -> SearchRequest:
        if self.providers is not None and len({provider.id for provider in self.providers}) != len(
            self.providers
        ):
            raise ValueError("providers must not contain duplicate ids")
        return self


class SearchIdentifier(CanonicalModel):
    """A stable domain identifier such as DOI or OpenAlex ID."""

    scheme: str = Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_.-]*$")
    value: str = Field(min_length=1, max_length=512)


class SearchAttributes(CanonicalModel):
    """Explicit additive metadata shared by the first Provider v2 slices."""

    year: int | None = Field(default=None, ge=0, le=9999)
    authors: tuple[str, ...] = ()
    identifiers: tuple[SearchIdentifier, ...] = ()
    resource_type: str | None = Field(default=None, min_length=1, max_length=64)
    language: str | None = Field(default=None, min_length=2, max_length=35)
    open_access: bool | None = None
    citation_count: int | None = Field(default=None, ge=0)

    @field_validator("authors")
    @classmethod
    def _authors_are_nonblank_and_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("authors must be nonblank and unique")
        return normalized


class SearchItem(CanonicalModel):
    """One normalized Search result without provider-private payloads."""

    id: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=2048)
    url: AnyHttpUrl | None = None
    snippet: str | None = Field(default=None, max_length=20_000)
    rank: int | None = Field(default=None, ge=1)
    provenance: tuple[Provenance, ...] = Field(min_length=1)
    attributes: SearchAttributes | None = None


class ProviderFailure(CanonicalModel):
    """A machine-readable provider failure retained in partial results."""

    provider: str = Field(min_length=1, max_length=128)
    code: CanonicalErrorCode


class SearchMeta(CanonicalModel):
    """Provider outcome summary for Search and LLM Search results."""

    partial: bool = False
    requested: tuple[str, ...] = ()
    succeeded: tuple[str, ...] = ()
    failed: tuple[ProviderFailure, ...] = ()

    @model_validator(mode="after")
    def _provider_outcomes_are_consistent(self) -> SearchMeta:
        requested = set(self.requested)
        succeeded = set(self.succeeded)
        failed = {item.provider for item in self.failed}
        if any(len(values) != len(set(values)) for values in (self.requested, self.succeeded)):
            raise ValueError("provider outcome IDs must be unique")
        if len(failed) != len(self.failed) or succeeded.intersection(failed):
            raise ValueError("provider outcomes must be unique and disjoint")
        if requested and not succeeded.union(failed).issubset(requested):
            raise ValueError("provider outcomes must belong to requested providers")
        if self.partial != bool(failed):
            raise ValueError("partial must reflect failed provider outcomes")
        return self


class SearchPage(CanonicalModel):
    """Canonical Search page emitted by a Search provider or Core module."""

    items: tuple[SearchItem, ...]
    page: PageInfo
    meta: SearchMeta
    context: RequestContext


LLMSearchStrategy: TypeAlias = Literal["single", "fanout", "first_success"]


class LLMFetchOptions(CanonicalModel):
    """Bounded request to enable a separately secured downstream Fetch step."""

    enabled: bool = True


class LLMSearchBudget(CanonicalModel):
    """Execution limits, not a billing promise."""

    timeout_seconds: float | None = Field(default=None, gt=0, le=120)
    max_attempts: int | None = Field(default=None, ge=1)


class LLMSearchRequest(CanonicalModel):
    """Canonical single-operation LLM Search input."""

    query: str = Field(min_length=1, max_length=4096)
    providers: tuple[ProviderRef, ...] = Field(min_length=1)
    strategy: LLMSearchStrategy
    max_results_per_provider: int | None = Field(default=None, ge=1)
    fetch: LLMFetchOptions | None = None
    budget: LLMSearchBudget | None = None
    synthesis_profile: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("query")
    @classmethod
    def _normalise_query(cls, value: str) -> str:
        normalised = value.strip()
        if not normalised:
            raise ValueError("query must not be blank")
        return normalised

    @model_validator(mode="after")
    def _unique_provider_ids(self) -> LLMSearchRequest:
        if len({provider.id for provider in self.providers}) != len(self.providers):
            raise ValueError("providers must not contain duplicate ids")
        return self


class EvidenceItem(CanonicalModel):
    """Verifiable public evidence attached to an LLM Search item."""

    id: str = Field(min_length=1, max_length=512)
    item_id: str = Field(min_length=1, max_length=512)
    provider: str = Field(min_length=1, max_length=128)
    public_url: AnyHttpUrl
    title_or_snippet: str = Field(min_length=1, max_length=20_000)
    retrieved_at: datetime


class LLMSearchResult(CanonicalModel):
    """Canonical LLM Search result with evidence and always-present usage."""

    query: str = Field(min_length=1, max_length=4096)
    items: tuple[SearchItem, ...]
    evidence: tuple[EvidenceItem, ...]
    answer: str | None = Field(default=None, max_length=100_000)
    meta: SearchMeta
    usage: Usage
    context: RequestContext

    @model_validator(mode="after")
    def _evidence_and_answer_are_traceable(self) -> LLMSearchResult:
        item_ids = {item.id for item in self.items}
        evidence_ids = {item.id for item in self.evidence}
        if len(item_ids) != len(self.items) or len(evidence_ids) != len(self.evidence):
            raise ValueError("item and evidence IDs must be unique")
        evidenced_item_ids = {item.item_id for item in self.evidence}
        if not item_ids.issubset(evidenced_item_ids) or not evidenced_item_ids.issubset(item_ids):
            raise ValueError("every item must have evidence and every evidence item must resolve")
        if self.answer:
            paragraphs = tuple(
                part.strip() for part in re.split(r"\n\s*\n", self.answer) if part.strip()
            )
            for paragraph in paragraphs:
                if not any(f"[{evidence_id}]" in paragraph for evidence_id in evidence_ids):
                    raise ValueError("each answer paragraph must cite a stable evidence ID")
        return self


FetchStrategy: TypeAlias = Literal["fallback", "fanout"]


class FetchContentOptions(CanonicalModel):
    """Bounded normalized-content extraction options."""

    max_code_points: int | None = Field(default=None, ge=1, le=1_000_000)


class FetchPolicyOptions(CanonicalModel):
    """Policy options that cannot disable server-side Fetch protections."""

    respect_robots: Literal[True] | None = None


class FetchRequest(CanonicalModel):
    """Canonical Fetch input; target validation does not replace SSRF controls."""

    targets: tuple[AnyHttpUrl, ...] = Field(min_length=1, max_length=20)
    providers: tuple[ProviderRef, ...] | None = None
    strategy: FetchStrategy | None = None
    content: FetchContentOptions | None = None
    policy: FetchPolicyOptions | None = None

    @model_validator(mode="after")
    def _unique_provider_ids(self) -> FetchRequest:
        if self.providers is not None and len({provider.id for provider in self.providers}) != len(
            self.providers
        ):
            raise ValueError("providers must not contain duplicate ids")
        return self


class FetchTargetRequest(CanonicalModel):
    """One policy-bounded target dispatched to a single FetchProvider."""

    target: AnyHttpUrl
    content: FetchContentOptions | None = None
    policy: FetchPolicyOptions | None = None


class ContentMetadata(CanonicalModel):
    """Safe normalized-content metadata for one Fetch result."""

    media_type: str = Field(min_length=1, max_length=128)
    charset: str | None = Field(default=None, min_length=1, max_length=64)
    retrieved_at: datetime | None = None
    truncated: bool
    content_length: int | None = Field(default=None, ge=0)
    quality: Literal["high", "low"] | None = None


class FetchResult(CanonicalModel):
    """One per-target Fetch outcome, including its own provenance or safe error."""

    target: AnyHttpUrl
    final_url: AnyHttpUrl | None = None
    status: Literal["success", "failed", "blocked"]
    title: str | None = Field(default=None, max_length=2048)
    content: str | None = Field(default=None, max_length=1_000_000)
    content_metadata: ContentMetadata | None = None
    provenance: tuple[Provenance, ...] = Field(min_length=1)
    error: ErrorDetail | None = None

    @model_validator(mode="after")
    def _outcome_is_internally_consistent(self) -> FetchResult:
        if self.status == "success":
            if self.content is None or not self.content.strip() or self.content_metadata is None:
                raise ValueError("successful fetch requires non-empty content and metadata")
            if self.error is not None:
                raise ValueError("successful fetch cannot include an error")
            expected_quality = "low" if len(self.content.strip()) <= 63 else "high"
            if self.content_metadata.quality != expected_quality:
                raise ValueError("content quality must match normalized content length")
        else:
            if self.error is None:
                raise ValueError("failed or blocked fetch requires an item error")
            if self.content is not None or self.content_metadata is not None:
                raise ValueError("failed or blocked fetch cannot include normalized content")
        return self


class FetchMeta(CanonicalModel):
    """Batch-level Fetch outcome summary."""

    partial: bool = False


class FetchBatch(CanonicalModel):
    """Canonical Fetch batch emitted by a Fetch provider or Core module."""

    items: tuple[FetchResult, ...]
    meta: FetchMeta
    context: RequestContext


__all__ = [
    "Capability",
    "CanonicalErrorCode",
    "CanonicalModel",
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
    "FetchStrategy",
    "FetchTargetRequest",
    "LLMFetchOptions",
    "LLMSearchBudget",
    "LLMSearchRequest",
    "LLMSearchResult",
    "LLMSearchStrategy",
    "PageInfo",
    "ProviderFailure",
    "ProviderProbe",
    "ProviderProvenance",
    "ProviderRef",
    "Provenance",
    "RequestContext",
    "SearchDomain",
    "SearchAttributes",
    "SearchFilters",
    "SearchIdentifier",
    "SearchItem",
    "SearchMeta",
    "SearchPage",
    "SearchPageRequest",
    "SearchRequest",
    "Usage",
    "UsageMetadata",
]
