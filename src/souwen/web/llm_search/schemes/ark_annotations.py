"""Volcengine Ark Responses annotations for model-bound web search sources."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar
from urllib.parse import urlsplit

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, ParseError, SourceUnavailableError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import (
    SearchCandidate,
    SearchSnippet,
    SearchSourceProvenance,
    WebSearchResponse,
    WebSearchResult,
)
from souwen.web.llm_search.base import (
    ConcreteSearchSourceSpec,
    ResolvedConcreteSearchConfig,
    SearchSchemeSpec,
    resolve_concrete_source_config,
)

ARK_ANNOTATIONS_SCHEME = SearchSchemeSpec(
    scheme_id="uniapi_ark_annotations_v1",
    gateway_id="uniapi",
    upstream_channel="volcengine_ark",
    protocol="responses",
    endpoint_kind="responses",
    tool_schema="ark_web_search_v1",
    candidate_contract="structured_result_list",
    default_timeout_seconds=45.0,
    source_grade=True,
    request_builder=lambda query, model_id, max_keyword=10: build_ark_request(
        query, model_id, max_keyword=max_keyword
    ),
    response_parser=lambda payload, provenance: parse_ark_annotations(payload, provenance),
)
ARK_ANNOTATIONS_DEEPSEEK = ConcreteSearchSourceSpec(
    source_id="uniapi_ark_annotations_deepseek_v3_2_251201",
    scheme_id=ARK_ANNOTATIONS_SCHEME.scheme_id,
    model_id="deepseek-v3-2-251201",
    last_verified_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
)
ARK_ANNOTATIONS_DOUBAO = ConcreteSearchSourceSpec(
    source_id="uniapi_ark_annotations_doubao_seed_2_0_lite_260428",
    scheme_id=ARK_ANNOTATIONS_SCHEME.scheme_id,
    model_id="doubao-seed-2-0-lite-260428",
    last_verified_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
)
ARK_ANNOTATIONS_SOURCES = (ARK_ANNOTATIONS_DEEPSEEK, ARK_ANNOTATIONS_DOUBAO)

_ARK_RESPONSE_PATH = "/v1/responses"
_ARK_MAX_KEYWORD_DEFAULT = 10
_ARK_MAX_RESULTS = 50


@dataclass(frozen=True, slots=True)
class ArkSearchReceipt:
    """Normalized candidates plus non-inferred receipt counters for one request."""

    candidates: tuple[SearchCandidate, ...]
    visible_search_calls: int
    provider_metered_search_calls: int | None


def build_ark_request(query: str, model_id: str, *, max_keyword: int = 10) -> dict[str, Any]:
    """Build the fixed Ark Responses payload; callers cannot supply a dynamic model."""
    if not query.strip() or not model_id.strip() or not 1 <= max_keyword <= 50:
        raise ValueError("invalid Ark search request")
    return {
        "model": model_id,
        "input": query.strip(),
        "tools": [{"type": "web_search", "max_keyword": max_keyword}],
    }


def _response_provenance(
    payload: Mapping[str, Any], provenance: SearchSourceProvenance
) -> SearchSourceProvenance:
    """Attach receipt metadata without retaining response IDs or raw payloads."""
    response_status = payload.get("status")
    incomplete_reason = payload.get("reason")
    served_model_id = payload.get("model")
    return provenance.model_copy(
        update={
            "served_model_id": served_model_id
            if isinstance(served_model_id, str) and served_model_id.strip()
            else provenance.served_model_id,
            "response_status": response_status
            if isinstance(response_status, str) and response_status.strip()
            else provenance.response_status,
            "partial": response_status == "incomplete" or provenance.partial,
            "incomplete_reason": incomplete_reason
            if isinstance(incomplete_reason, str) and incomplete_reason.strip()
            else provenance.incomplete_reason,
            "search_call_status": "completed",
        }
    )


def _completed_ark_search_call(payload: Mapping[str, Any]) -> bool:
    output = payload.get("output")
    if not isinstance(output, list):
        return False
    return any(
        isinstance(item, Mapping)
        and item.get("type") == "web_search_call"
        and item.get("status") == "completed"
        for item in output
    )


def _visible_ark_search_call_count(payload: Mapping[str, Any]) -> int:
    """Count response-visible calls; do not derive billing usage from this count."""
    output = payload.get("output")
    if not isinstance(output, list):
        return 0
    return sum(
        isinstance(item, Mapping) and item.get("type") == "web_search_call" for item in output
    )


def _message_annotations(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return only structured ``output[].message.content[].annotations`` values."""
    output = payload.get("output")
    if not isinstance(output, list):
        return []
    annotations: list[Mapping[str, Any]] = []
    for item in output:
        if not isinstance(item, Mapping) or item.get("status") not in {"completed", "incomplete"}:
            continue
        message = item.get("message")
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            part_annotations = part.get("annotations")
            if not isinstance(part_annotations, list):
                continue
            annotations.extend(
                annotation for annotation in part_annotations if isinstance(annotation, Mapping)
            )
    return annotations


def parse_ark_annotations(
    payload: Mapping[str, Any], provenance: SearchSourceProvenance
) -> list[SearchCandidate]:
    """Parse a verified Ark search receipt; never infer entries from answer text."""
    if not _completed_ark_search_call(payload):
        raise ValueError("Ark response has no completed web_search_call")

    resolved_provenance = _response_provenance(payload, provenance)
    candidates: list[SearchCandidate] = []
    for annotation in _message_annotations(payload):
        if annotation.get("type") != "url_citation":
            continue
        url = annotation.get("url")
        title = annotation.get("title")
        if not isinstance(url, str) or not isinstance(title, str) or not title.strip():
            continue
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        summary = annotation.get("summary")
        candidates.append(
            SearchCandidate(
                title=title.strip(),
                url=url,
                provider_snippet=(
                    SearchSnippet(
                        text=summary,
                        type="provider_summary",
                        provider="volcengine_ark",
                    )
                    if isinstance(summary, str) and summary.strip()
                    else None
                ),
                published_at=annotation.get("publish_time")
                if isinstance(annotation.get("publish_time"), str)
                else None,
                site_name=annotation.get("site_name")
                if isinstance(annotation.get("site_name"), str)
                else None,
                favicon_url=annotation.get("logo_url")
                if isinstance(annotation.get("logo_url"), str)
                else None,
                provenance=resolved_provenance,
            )
        )
    if not candidates:
        raise ValueError("Ark response has no valid completed search annotations")
    return candidates


def _positive_bounded_int(value: object, *, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


class ArkAnnotationsClient(SouWenHttpClient):
    """Base client for a single immutable Ark concrete source."""

    SOURCE_SPEC: ClassVar[ConcreteSearchSourceSpec]

    def __init__(self) -> None:
        self.resolved = self._resolve_config()
        if not self.resolved.enabled:
            raise SourceUnavailableError(f"source {self.resolved.source_id} is disabled")
        if self.resolved.missing_fields:
            raise ConfigError(
                self.resolved.missing_fields[0],
                "UniAPI Ark search gateway",
            )
        super().__init__(
            base_url=self.resolved.base_url or "",
            headers={
                "Authorization": f"Bearer {self.resolved.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.resolved.timeout_seconds,
            source_name=self.resolved.source_id,
        )

    @classmethod
    def _resolve_config(cls) -> ResolvedConcreteSearchConfig:
        return resolve_concrete_source_config(get_config(), ARK_ANNOTATIONS_SCHEME, cls.SOURCE_SPEC)

    def _provenance(self) -> SearchSourceProvenance:
        return SearchSourceProvenance(
            source_id=self.resolved.source_id,
            scheme_id=self.resolved.scheme_id,
            gateway_id=self.resolved.gateway_id,
            upstream_channel=ARK_ANNOTATIONS_SCHEME.upstream_channel,
            requested_model_id=self.resolved.model_id,
            protocol=ARK_ANNOTATIONS_SCHEME.protocol,
            tool_schema=ARK_ANNOTATIONS_SCHEME.tool_schema,
        )

    async def search_candidate_receipt(self, query: str, max_results: int = 10) -> ArkSearchReceipt:
        """Execute one request and return candidates plus only observed usage evidence."""
        max_keyword = _positive_bounded_int(
            self.resolved.params.get("max_keyword"),
            default=_ARK_MAX_KEYWORD_DEFAULT,
            maximum=_ARK_MAX_RESULTS,
        )
        payload = build_ark_request(query, self.resolved.model_id, max_keyword=max_keyword)
        response = await self.post(
            _ARK_RESPONSE_PATH,
            json=payload,
            retry_policy="single_attempt",
        )
        try:
            response_payload = response.json()
        except Exception as exc:
            raise ParseError("Ark annotation response is not valid JSON") from exc
        if not isinstance(response_payload, Mapping):
            raise ParseError("Ark annotation response must be an object")
        try:
            parsed = parse_ark_annotations(response_payload, self._provenance())
        except ValueError as exc:
            raise ParseError(
                "Ark annotation response does not meet the retrieval contract"
            ) from exc

        unique: list[SearchCandidate] = []
        seen_urls: set[str] = set()
        for candidate in parsed:
            key = candidate.url.rstrip("/").lower()
            if key in seen_urls:
                continue
            seen_urls.add(key)
            unique.append(candidate)
        return ArkSearchReceipt(
            candidates=tuple(
                unique[: _positive_bounded_int(max_results, default=10, maximum=_ARK_MAX_RESULTS)]
            ),
            visible_search_calls=_visible_ark_search_call_count(response_payload),
            # The verified Ark receipt shape does not expose a stable metered-search field.
            # Keep it unknown instead of equating visible calls with billable usage.
            provider_metered_search_calls=None,
        )

    async def search_candidates(self, query: str, max_results: int = 10) -> list[SearchCandidate]:
        """Execute one billable Ark request and return strict internal candidates."""
        receipt = await self.search_candidate_receipt(query, max_results=max_results)
        return list(receipt.candidates)

    async def search(self, query: str, max_results: int = 10) -> WebSearchResponse:
        """Project strict candidates into the unchanged legacy web-search response."""
        candidates = await self.search_candidates(query, max_results=max_results)
        results = [
            WebSearchResult(
                source=self.resolved.source_id,
                title=candidate.title or "",
                url=candidate.url,
                snippet=candidate.provider_snippet.text if candidate.provider_snippet else "",
                engine=self.resolved.source_id,
                raw={
                    "search_candidate": candidate.model_dump(mode="json"),
                },
            )
            for candidate in candidates
        ]
        return WebSearchResponse(
            query=query,
            source=self.resolved.source_id,
            results=results,
            total_results=len(results),
        )


class UniApiArkAnnotationsDeepSeekClient(ArkAnnotationsClient):
    """Ark annotations source bound to DeepSeek V3.2's exact gateway model ID."""

    SOURCE_SPEC = ARK_ANNOTATIONS_DEEPSEEK


class UniApiArkAnnotationsDoubaoClient(ArkAnnotationsClient):
    """Ark annotations source bound to Doubao Seed 2.0 Lite's exact gateway model ID."""

    SOURCE_SPEC = ARK_ANNOTATIONS_DOUBAO
