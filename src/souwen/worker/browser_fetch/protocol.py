"""Versioned loopback contract shared by the API runtime and Browser Worker."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


BROWSER_WORKER_CONTRACT_MAJOR = 1
BROWSER_WORKER_DEFAULT_PORT = 49266
BROWSER_WORKER_MAX_DEADLINE_SECONDS = 120.0
BROWSER_WORKER_MAX_CODE_POINTS = 1_000_000
BROWSER_WORKER_DEFAULT_CODE_POINTS = 200_000
BROWSER_WORKER_PAGE_SLOTS = 2


class WorkerModel(BaseModel):
    """Strict immutable internal transport model."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class WorkerRuntimeEvidence(WorkerModel):
    """Non-secret Worker identity required for readiness and every fetch receipt."""

    contract_major: Literal[1] = 1
    source_sha: str = Field(min_length=7, max_length=64, pattern=r"^[0-9a-f]+$")
    runtime_version: str = Field(min_length=1, max_length=64)
    config_revision: str = Field(min_length=1, max_length=128)
    provider_inventory_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class WorkerFetchRequest(WorkerModel):
    """Exactly one selected browser execution for one canonical Fetch target."""

    execution_mode: Literal["playwright"] = "playwright"
    provider: Literal["builtin-fetch"] = "builtin-fetch"
    target: AnyHttpUrl
    max_code_points: int = Field(
        default=BROWSER_WORKER_DEFAULT_CODE_POINTS,
        ge=1,
        le=BROWSER_WORKER_MAX_CODE_POINTS,
    )


class WorkerFetchItem(WorkerModel):
    """Bounded normalized browser output without raw page data."""

    final_url: AnyHttpUrl
    title: str | None = Field(default=None, max_length=2048)
    content: str = Field(min_length=1, max_length=BROWSER_WORKER_MAX_CODE_POINTS)
    media_type: str = Field(min_length=1, max_length=128)
    charset: str | None = Field(default=None, min_length=1, max_length=64)
    retrieved_at: datetime
    truncated: bool
    content_length: int = Field(ge=1)
    quality: Literal["high", "low"]

    @model_validator(mode="after")
    def _content_is_nonblank_and_quality_matches(self) -> WorkerFetchItem:
        normalized_length = len(self.content.strip())
        if normalized_length == 0:
            raise ValueError("browser content must not be blank")
        expected = "low" if normalized_length <= 63 else "high"
        if self.quality != expected:
            raise ValueError("browser content quality does not match normalized length")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return self


class WorkerFetchResponse(WorkerModel):
    """Successful authenticated loopback receipt."""

    request_id: str = Field(min_length=1, max_length=128)
    contract_major: Literal[1] = 1
    evidence: WorkerRuntimeEvidence
    item: WorkerFetchItem


WorkerErrorCode: TypeAlias = Literal[
    "worker_unauthorized",
    "worker_invalid_request",
    "worker_protocol_mismatch",
    "worker_overloaded",
    "worker_timeout",
    "worker_unavailable",
    "worker_not_ready",
    "policy_blocked",
    "empty_content",
]


class WorkerErrorDetail(WorkerModel):
    """Stable redacted internal error."""

    code: WorkerErrorCode
    message: str = Field(min_length=1, max_length=256)
    retryable: bool
    request_id: str = Field(min_length=1, max_length=128)


class WorkerErrorResponse(WorkerModel):
    """Internal error envelope."""

    error: WorkerErrorDetail
    contract_major: Literal[1] = 1


class WorkerProbeResponse(WorkerModel):
    """Authenticated Worker health/readiness receipt."""

    request_id: str = Field(min_length=1, max_length=128)
    status: Literal["alive", "ready", "not_ready"]
    ready: bool
    evidence: WorkerRuntimeEvidence


__all__ = [
    "BROWSER_WORKER_CONTRACT_MAJOR",
    "BROWSER_WORKER_DEFAULT_CODE_POINTS",
    "BROWSER_WORKER_DEFAULT_PORT",
    "BROWSER_WORKER_MAX_CODE_POINTS",
    "BROWSER_WORKER_MAX_DEADLINE_SECONDS",
    "BROWSER_WORKER_PAGE_SLOTS",
    "WorkerErrorCode",
    "WorkerErrorDetail",
    "WorkerErrorResponse",
    "WorkerFetchItem",
    "WorkerFetchRequest",
    "WorkerFetchResponse",
    "WorkerProbeResponse",
    "WorkerRuntimeEvidence",
]
