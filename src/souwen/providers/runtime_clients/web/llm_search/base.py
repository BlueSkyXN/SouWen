"""LLM-search scheme/source identity, configuration, timeout, and budget contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
import re
import time
from types import MappingProxyType
from typing import Any, get_args, Literal, TYPE_CHECKING

from souwen.config.models import LLM_SEARCH_IDENTITY_PARAMS

if TYPE_CHECKING:
    from souwen.config import SouWenConfig


CandidateContract = Literal[
    "structured_result_list",
    "citation_and_url_candidates",
    "metadata_result_list",
    "url_candidates",
    "opaque_answer_only",
]
Stability = Literal["stable", "beta", "experimental", "deprecated"]
Primitive = str | int | float | bool
SchemeCallable = Callable[..., Any]

_CANDIDATE_CONTRACTS = frozenset(get_args(CandidateContract))
_STABILITIES = frozenset(get_args(Stability))
_SLUG_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")
_VERSIONED_SCHEME_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*_v[1-9][0-9]*\Z")


def _require_slug(value: str, *, field_name: str, versioned: bool = False) -> None:
    pattern = _VERSIONED_SCHEME_RE if versioned else _SLUG_RE
    if not value or pattern.fullmatch(value) is None:
        suffix = " and end with _vN" if versioned else ""
        raise ValueError(f"{field_name} must be lowercase snake-case{suffix}: {value!r}")


def gateway_credential_fields(gateway_id: str) -> tuple[str, str]:
    """Return stable, value-free config paths for a shared gateway."""
    _require_slug(gateway_id, field_name="gateway_id")
    prefix = f"llm_search_gateways.{gateway_id}"
    return (f"{prefix}.api_key", f"{prefix}.base_url")


@dataclass(frozen=True, slots=True)
class SearchSchemeSpec:
    """Reusable wire-contract declaration; it is not a user-selectable source."""

    scheme_id: str
    gateway_id: str
    upstream_channel: str
    protocol: str
    endpoint_kind: str
    tool_schema: str
    candidate_contract: CandidateContract
    default_timeout_seconds: float
    source_grade: bool
    request_builder: SchemeCallable | None = field(default=None, repr=False, compare=False)
    response_parser: SchemeCallable | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_slug(self.scheme_id, field_name="scheme_id", versioned=True)
        _require_slug(self.gateway_id, field_name="gateway_id")
        for field_name in ("upstream_channel", "protocol", "endpoint_kind", "tool_schema"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.candidate_contract not in _CANDIDATE_CONTRACTS:
            raise ValueError(f"unsupported candidate_contract: {self.candidate_contract!r}")
        if not isinstance(self.source_grade, bool):
            raise ValueError("source_grade must be a bool")
        if not 1.0 <= float(self.default_timeout_seconds) <= 300.0:
            raise ValueError("default_timeout_seconds must be within 1..300 seconds")
        hooks = (self.request_builder is not None, self.response_parser is not None)
        if any(hooks) and not all(hooks):
            raise ValueError("request_builder and response_parser must be provided together")
        if all(hooks) and not callable(self.request_builder):
            raise ValueError("request_builder must be callable")
        if all(hooks) and not callable(self.response_parser):
            raise ValueError("response_parser must be callable")

    @property
    def executable(self) -> bool:
        return (
            self.source_grade
            and self.request_builder is not None
            and self.response_parser is not None
        )


@dataclass(frozen=True, slots=True)
class ConcreteSearchSourceSpec:
    """Immutable source identity: exactly one scheme and requested model."""

    source_id: str
    scheme_id: str
    model_id: str
    stability: Stability = "experimental"
    default_enabled: bool = False
    timeout_seconds: float | None = None
    last_verified_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_slug(self.source_id, field_name="source_id")
        _require_slug(self.scheme_id, field_name="scheme_id", versioned=True)
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be a non-empty exact upstream model ID")
        if self.model_id != self.model_id.strip():
            raise ValueError("model_id must not have leading or trailing whitespace")
        if self.stability not in _STABILITIES:
            raise ValueError(f"unsupported stability: {self.stability!r}")
        if not isinstance(self.default_enabled, bool):
            raise ValueError("default_enabled must be a bool")
        if self.stability == "experimental" and self.default_enabled:
            raise ValueError("experimental LLM-search sources must default to disabled")
        if self.timeout_seconds is not None and not 1.0 <= float(self.timeout_seconds) <= 300.0:
            raise ValueError("timeout_seconds must be within 1..300 seconds")
        if self.last_verified_at is not None and self.last_verified_at.tzinfo is None:
            raise ValueError("last_verified_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ResolvedConcreteSearchConfig:
    """Secret-safe runtime projection for one concrete source."""

    source_id: str
    scheme_id: str
    gateway_id: str
    model_id: str
    enabled: bool
    timeout_seconds: float
    missing_fields: tuple[str, ...]
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = field(default=None, repr=False)
    params: Mapping[str, Primitive] = field(
        default_factory=lambda: MappingProxyType({}), repr=False
    )

    @property
    def available(self) -> bool:
        return self.enabled and not self.missing_fields


def resolve_concrete_source_config(
    config: SouWenConfig,
    scheme: SearchSchemeSpec,
    source: ConcreteSearchSourceSpec,
) -> ResolvedConcreteSearchConfig:
    """Resolve source override and shared gateway without exposing identity overrides."""
    if source.scheme_id != scheme.scheme_id:
        raise ValueError(
            f"source {source.source_id!r} references {source.scheme_id!r}, "
            f"not scheme {scheme.scheme_id!r}"
        )

    source_config = config.get_source_config(source.source_id)
    params = dict(source_config.params)
    forbidden = sorted(LLM_SEARCH_IDENTITY_PARAMS.intersection(params))
    if forbidden:
        raise ValueError(
            f"source {source.source_id!r} cannot override immutable fields: {', '.join(forbidden)}"
        )

    api_key = config.resolve_llm_search_gateway_field(
        source.source_id, scheme.gateway_id, "api_key"
    )
    base_url = config.resolve_llm_search_gateway_field(
        source.source_id, scheme.gateway_id, "base_url"
    )
    credential_fields = gateway_credential_fields(scheme.gateway_id)
    missing_fields = tuple(
        field_name
        for field_name, value in zip(credential_fields, (api_key, base_url), strict=True)
        if not value
    )

    enabled = config.is_source_enabled(source.source_id, default=source.default_enabled)
    timeout = (
        source_config.timeout
        if source_config.timeout is not None
        else source.timeout_seconds
        if source.timeout_seconds is not None
        else scheme.default_timeout_seconds
    )
    return ResolvedConcreteSearchConfig(
        source_id=source.source_id,
        scheme_id=scheme.scheme_id,
        gateway_id=scheme.gateway_id,
        model_id=source.model_id,
        enabled=enabled,
        timeout_seconds=float(timeout),
        missing_fields=missing_fields,
        api_key=api_key,
        base_url=base_url,
        params=MappingProxyType(params),
    )


@dataclass(slots=True)
class SearchDeadlineBudget:
    """One monotonic deadline shared by every source attempt in a search stage."""

    total_seconds: float
    _clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    _started_at: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not 0.0 < float(self.total_seconds) <= 300.0:
            raise ValueError("total_seconds must be within (0, 300]")
        self._started_at = self._clock()

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, float(self.total_seconds) - (self._clock() - self._started_at))

    @property
    def expired(self) -> bool:
        return self.remaining_seconds <= 0.0

    def timeout_for(self, requested_seconds: float) -> float:
        """Cap one attempt by remaining budget; fail before sending after expiry."""
        if requested_seconds <= 0:
            raise ValueError("requested_seconds must be positive")
        remaining = self.remaining_seconds
        if remaining <= 0:
            raise TimeoutError("search-stage deadline exhausted")
        return min(float(requested_seconds), remaining)
