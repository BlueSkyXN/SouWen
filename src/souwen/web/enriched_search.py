"""Search-to-fetch enrichment behind the additive enriched-search API contract.

The legacy :func:`web_search` facade intentionally projects failed engines to an
empty result list.  That is the right compatibility behaviour for ``GET
/search/web`` but not enough evidence for the enriched API, which has to report
per-source outcomes and enforce an endpoint-wide deadline.  Explicit concrete
LLM-search sources therefore run through their Registry adapters here; the
legacy path remains available for the existing Python helper and tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from souwen.config import get_config
from souwen.core.redaction import redact_secret_text
from souwen.editions import ensure_source_allowed
from souwen.llm.enriched_synthesis import (
    resolve_enriched_synthesis_profile,
    synthesize_enriched_results,
)
from souwen.llm.models import EnrichedSynthesisAnswer, LLMUsage
from souwen.models import (
    EnrichedWebSearchResult,
    FetchResult,
    SearchCandidate,
    SearchSnippet,
    SearchSourceProvenance,
)
from souwen.registry import get as get_source_adapter
from souwen.registry.adapter import SourceAdapter
from souwen.registry.meta import missing_credential_fields, source_config_validation_reason
from souwen.web.fetch import fetch_content
from souwen.web.llm_search import SearchDeadlineBudget
from souwen.web.search import web_search

SourceOutcome = Literal["success_with_results", "success_empty", "timeout", "failed"]
SourceStrategy = Literal["single", "fanout", "first_success"]
SynthesisStatus = Literal["not_requested", "success", "failed", "skipped"]

logger = logging.getLogger("souwen.web.enriched_search")


class EnrichedSearchError(RuntimeError):
    """Base error for safe, route-mappable enriched-search failures."""


class EnrichedSearchSourceValidationError(EnrichedSearchError):
    """The caller selected a source that is not an allowed concrete source."""


class EnrichedSearchUnknownSourceError(EnrichedSearchSourceValidationError):
    """The caller selected a Registry source ID that does not exist."""


class EnrichedSearchSourceDisabledError(EnrichedSearchError):
    """The selected concrete source is disabled by its explicit runtime policy."""


class EnrichedSearchUnavailableError(EnrichedSearchError):
    """Every attempted source failed before producing a valid candidate."""


class EnrichedSearchDeadlineExceeded(EnrichedSearchError):
    """The shared search-stage deadline was consumed by source attempts."""


@dataclass(frozen=True, slots=True)
class EnrichedSourceAttempt:
    """Safe receipt summary for one source attempt; provider raw is never retained."""

    source_id: str
    attempt_index: int
    outcome: SourceOutcome
    visible_search_calls: int | None = None
    provider_metered_search_calls: int | None = None


@dataclass(frozen=True, slots=True)
class _SourceExecution:
    candidates: tuple[SearchCandidate, ...]
    attempt: EnrichedSourceAttempt


@dataclass(frozen=True, slots=True)
class EnrichedSearchExecution:
    """Python-level result consumed by the REST route without provider raw data."""

    query: str
    results: list[EnrichedWebSearchResult]
    source_outcomes: dict[str, SourceOutcome]
    discarded_candidates: int
    source_attempts: tuple[EnrichedSourceAttempt, ...] = ()
    visible_search_calls: int = 0
    provider_metered_search_calls: int | None = None
    fetched_pages: int = 0
    synthesis_status: SynthesisStatus = "not_requested"
    answer: EnrichedSynthesisAnswer | None = None
    summary_usage: LLMUsage | None = None

    @property
    def partial(self) -> bool:
        """Whether at least one source failed while another source completed."""
        outcomes = set(self.source_outcomes.values())
        return bool(outcomes & {"success_with_results", "success_empty"}) and bool(
            outcomes & {"failed", "timeout"}
        )


def _canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, "")
    )


def _excerpt(content: str, limit: int) -> str:
    content = " ".join(content.split())
    return content[:limit].rstrip()


def _candidate_from_result(result: object) -> SearchCandidate:
    """Reuse a provider's normalized candidate when its legacy projection has one."""
    raw = getattr(result, "raw", {})
    if isinstance(raw, Mapping):
        candidate = raw.get("search_candidate")
        if isinstance(candidate, Mapping):
            try:
                return SearchCandidate.model_validate(candidate)
            except (TypeError, ValueError):
                # The enriched API can fall back to the public legacy projection,
                # but never exposes the invalid provider payload.
                pass

    title = getattr(result, "title", "")
    url = getattr(result, "url", "")
    source = getattr(result, "source", "")
    snippet = getattr(result, "snippet", "")
    return SearchCandidate(
        title=title if isinstance(title, str) else None,
        url=url,
        provider_snippet=(
            SearchSnippet(text=snippet, type="provider_snippet", provider=source)
            if isinstance(snippet, str) and snippet.strip()
            else None
        ),
        provenance=SearchSourceProvenance(
            source_id=source,
            scheme_id="registry_adapter",
            requested_model_id=None,
        ),
    )


def _with_attempt_metadata(
    candidates: Iterable[SearchCandidate],
    *,
    source_id: str,
    attempt_index: int,
    source_strategy: SourceStrategy,
) -> tuple[SearchCandidate, ...]:
    """Attach dispatch evidence without accepting a provider-supplied strategy."""
    return tuple(
        candidate.model_copy(
            update={
                "provenance": candidate.provenance.model_copy(
                    update={
                        "source_id": source_id,
                        "attempt_index": attempt_index,
                        "source_strategy": source_strategy,
                    }
                )
            }
        )
        for candidate in candidates
    )


def _normalize_sources(sources: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for source in sources:
        if not isinstance(source, str) or not source.strip():
            raise EnrichedSearchSourceValidationError("sources 必须包含非空 source ID")
        normalized.append(source.strip())
    if not normalized:
        raise EnrichedSearchSourceValidationError("sources 至少需要一个 concrete source ID")
    if len(set(normalized)) != len(normalized):
        raise EnrichedSearchSourceValidationError("sources 不能包含重复 source ID")
    return normalized


def _validate_concrete_sources(sources: Iterable[str]) -> list[tuple[str, SourceAdapter]]:
    """Validate the public source allowlist before any provider import or request."""
    cfg = get_config()
    selected: list[tuple[str, SourceAdapter]] = []
    for source_id in _normalize_sources(sources):
        adapter = get_source_adapter(source_id)
        if adapter is None:
            raise EnrichedSearchUnknownSourceError(f"未知 enriched search source: {source_id}")
        if adapter.llm_search_identity is None or "search" not in adapter.capabilities:
            raise EnrichedSearchSourceValidationError(
                f"source {source_id!r} 不是可用于 enriched search 的 concrete source"
            )
        ensure_source_allowed(adapter, cfg.edition)
        if not cfg.is_source_enabled(source_id, default=adapter.runtime_default_enabled):
            raise EnrichedSearchSourceDisabledError(f"source {source_id!r} 已禁用")
        reason = source_config_validation_reason(cfg, source_id, adapter)
        if reason:
            raise EnrichedSearchSourceValidationError(reason)
        missing_fields = missing_credential_fields(cfg, source_id, adapter)
        if missing_fields:
            raise EnrichedSearchSourceValidationError(
                f"source {source_id!r} 缺少必需配置: {', '.join(missing_fields)}"
            )
        selected.append((source_id, adapter))
    return selected


def _effective_source_timeout_seconds(source_id: str, adapter: SourceAdapter) -> float:
    """Resolve the configured source override before applying the shared deadline."""
    configured_timeout = get_config().get_source_config(source_id).timeout
    return float(configured_timeout or adapter.methods["search"].timeout_seconds or 15.0)


async def _execute_concrete_source(
    *,
    source_id: str,
    adapter: SourceAdapter,
    query: str,
    max_results: int,
    deadline: SearchDeadlineBudget,
    source_strategy: SourceStrategy,
    attempt_index: int,
) -> _SourceExecution:
    """Run one Registry adapter once and map every provider failure to a safe outcome."""
    try:
        timeout_seconds = deadline.timeout_for(
            _effective_source_timeout_seconds(source_id, adapter)
        )
    except TimeoutError:
        return _SourceExecution(
            candidates=(),
            attempt=EnrichedSourceAttempt(source_id, attempt_index, "timeout"),
        )
    try:
        client_cls = adapter.client_loader()
        async with client_cls() as client:
            receipt_method = getattr(client, "search_candidate_receipt", None)
            if callable(receipt_method):
                receipt = await asyncio.wait_for(
                    receipt_method(query, max_results=max_results), timeout=timeout_seconds
                )
                candidates = tuple(getattr(receipt, "candidates", ()))
                visible_calls = getattr(receipt, "visible_search_calls", None)
                metered_calls = getattr(receipt, "provider_metered_search_calls", None)
            else:
                response = await asyncio.wait_for(
                    client.search(query, max_results=max_results), timeout=timeout_seconds
                )
                candidates = tuple(_candidate_from_result(result) for result in response.results)
                visible_calls = None
                metered_calls = None
    except (asyncio.TimeoutError, TimeoutError):
        return _SourceExecution(
            candidates=(),
            attempt=EnrichedSourceAttempt(source_id, attempt_index, "timeout"),
        )
    except Exception:
        return _SourceExecution(
            candidates=(),
            attempt=EnrichedSourceAttempt(source_id, attempt_index, "failed"),
        )

    normalized = _with_attempt_metadata(
        candidates,
        source_id=source_id,
        attempt_index=attempt_index,
        source_strategy=source_strategy,
    )
    return _SourceExecution(
        candidates=normalized,
        attempt=EnrichedSourceAttempt(
            source_id=source_id,
            attempt_index=attempt_index,
            outcome="success_with_results" if normalized else "success_empty",
            visible_search_calls=visible_calls if isinstance(visible_calls, int) else None,
            provider_metered_search_calls=metered_calls if isinstance(metered_calls, int) else None,
        ),
    )


async def _search_explicit_concrete_sources(
    *,
    query: str,
    sources: Iterable[str],
    source_strategy: SourceStrategy,
    max_results_per_source: int,
    max_source_attempts: int,
    deadline_seconds: float,
) -> tuple[list[SearchCandidate], dict[str, SourceOutcome], tuple[EnrichedSourceAttempt, ...]]:
    if source_strategy not in {"single", "fanout", "first_success"}:
        raise EnrichedSearchSourceValidationError("source_strategy 无效")
    selected = _validate_concrete_sources(sources)
    if source_strategy == "single" and len(selected) != 1:
        raise EnrichedSearchSourceValidationError(
            "source_strategy=single 时必须恰好选择一个 source"
        )
    if source_strategy == "fanout" and max_source_attempts < len(selected):
        raise EnrichedSearchSourceValidationError(
            "fanout 的 max_source_attempts 不得小于 sources 数量"
        )
    if max_source_attempts < 1:
        raise EnrichedSearchSourceValidationError("max_source_attempts 必须为正数")

    deadline = SearchDeadlineBudget(deadline_seconds)
    executions: list[_SourceExecution]
    if source_strategy == "fanout":
        executions = list(
            await asyncio.gather(
                *(
                    _execute_concrete_source(
                        source_id=source_id,
                        adapter=adapter,
                        query=query,
                        max_results=max_results_per_source,
                        deadline=deadline,
                        source_strategy=source_strategy,
                        attempt_index=index,
                    )
                    for index, (source_id, adapter) in enumerate(selected, start=1)
                )
            )
        )
    else:
        executions = []
        for index, (source_id, adapter) in enumerate(selected[:max_source_attempts], start=1):
            execution = await _execute_concrete_source(
                source_id=source_id,
                adapter=adapter,
                query=query,
                max_results=max_results_per_source,
                deadline=deadline,
                source_strategy=source_strategy,
                attempt_index=index,
            )
            executions.append(execution)
            if (
                source_strategy == "first_success"
                and execution.attempt.outcome == "success_with_results"
            ):
                break

    attempts = tuple(execution.attempt for execution in executions)
    outcomes = {attempt.source_id: attempt.outcome for attempt in attempts}
    if not any(outcome.startswith("success_") for outcome in outcomes.values()):
        if deadline.expired:
            raise EnrichedSearchDeadlineExceeded("enriched search 共享 deadline 已耗尽")
        raise EnrichedSearchUnavailableError("所有 enriched search source 均不可用")
    candidates = [candidate for execution in executions for candidate in execution.candidates]
    return candidates, outcomes, attempts


def _legacy_search_candidates(
    response: object,
    engines: list[str] | str | None,
) -> tuple[list[SearchCandidate], dict[str, SourceOutcome], tuple[EnrichedSourceAttempt, ...]]:
    candidates = [_candidate_from_result(result) for result in getattr(response, "results", ())]
    outcomes: dict[str, SourceOutcome] = {}
    for candidate in candidates:
        outcomes[candidate.provenance.source_id] = "success_with_results"
    if engines is not None:
        requested = [engines] if isinstance(engines, str) else engines
        for source_id in requested:
            outcomes.setdefault(source_id, "success_empty")
    attempts = tuple(
        EnrichedSourceAttempt(source_id, index, outcome)
        for index, (source_id, outcome) in enumerate(outcomes.items(), start=1)
    )
    return candidates, outcomes, attempts


async def enriched_web_search(
    query: str,
    engines: list[str] | str | None = None,
    *,
    sources: list[str] | tuple[str, ...] | None = None,
    source_strategy: SourceStrategy = "single",
    max_results_per_engine: int = 10,
    max_results_per_source: int | None = None,
    max_source_attempts: int = 1,
    deadline_seconds: float = 120.0,
    deduplicate: bool = True,
    fetch: bool = True,
    fetch_providers: list[str] | str | None = None,
    fetch_strategy: Literal["fallback", "fanout"] = "fallback",
    max_pages: int = 5,
    fetch_timeout: float = 30.0,
    include_content: bool = False,
    max_content_chars: int = 4_000,
    excerpt_chars: int = 500,
    synthesis_profile: str | None = None,
) -> EnrichedSearchExecution:
    """Return title/URL-gated results through the existing SSRF-safe fetch pipeline.

    ``sources`` activates the new explicit concrete-source contract.  ``engines``
    remains solely for backwards-compatible Python callers and keeps the legacy
    ``web_search`` aggregation semantics intact.
    """
    if sources is not None and engines is not None:
        raise ValueError("sources 与 engines 不能同时指定")
    if not 1 <= max_pages <= 100:
        raise ValueError("max_pages 必须在 1..100 范围内")
    if max_content_chars < 1 or excerpt_chars < 1:
        raise ValueError("content/excerpt 长度必须为正数")
    if not 1.0 <= float(deadline_seconds) <= 300.0:
        raise ValueError("deadline_seconds 必须在 1..300 秒范围内")

    # Resolve the request-selected profile before any upstream work.  There is
    # intentionally no default model/profile fallback for this paid stage.
    profile = (
        resolve_enriched_synthesis_profile(synthesis_profile)
        if synthesis_profile is not None
        else None
    )
    endpoint_budget = SearchDeadlineBudget(deadline_seconds)

    if sources is None:
        response = await web_search(
            query,
            engines=engines,
            max_results_per_engine=max_results_per_engine,
            deduplicate=False,
        )
        candidates, source_outcomes, source_attempts = _legacy_search_candidates(response, engines)
    else:
        candidates, source_outcomes, source_attempts = await _search_explicit_concrete_sources(
            query=query,
            sources=sources,
            source_strategy=source_strategy,
            max_results_per_source=max_results_per_source or max_results_per_engine,
            max_source_attempts=max_source_attempts,
            deadline_seconds=endpoint_budget.timeout_for(deadline_seconds),
        )

    grouped: dict[str, list[SearchCandidate]] = {}
    for index, candidate in enumerate(candidates):
        key = _canonical_url(candidate.url) if deduplicate else f"{index}:{candidate.url}"
        grouped.setdefault(key, []).append(candidate)

    fetch_by_discovery_url: dict[str, list[FetchResult]] = {}
    if fetch and grouped:
        discovery_keys = list(grouped)[:max_pages]
        urls = [grouped[key][0].url for key in discovery_keys]
        try:
            fetched = await fetch_content(
                urls,
                providers=fetch_providers,
                strategy=fetch_strategy,
                timeout=endpoint_budget.timeout_for(fetch_timeout),
                max_length=max_content_chars,
            )
        except TimeoutError as exc:
            raise EnrichedSearchDeadlineExceeded("enriched search 共享 deadline 已耗尽") from exc
        requested_urls = {_canonical_url(url) for url in urls}
        for item in fetched.results:
            discovery_url = _canonical_url(item.url)
            if discovery_url in requested_urls:
                fetch_by_discovery_url.setdefault(discovery_url, []).append(item)

    final_groups: dict[
        str, list[tuple[list[SearchCandidate], FetchResult | None, FetchResult | None]]
    ] = {}
    final_urls: dict[str, str] = {}
    for key, discoveries in grouped.items():
        fetch_results = fetch_by_discovery_url.get(_canonical_url(discoveries[0].url), [])
        fetched = next((item for item in fetch_results if item.error is None), None)
        failed_fetch = next((item for item in fetch_results if item.error), None)
        fetch_ok = fetched is not None and fetched.error is None
        final_url = (
            _canonical_url(fetched.final_url)
            if fetch_ok and fetched is not None
            else _canonical_url(discoveries[0].url)
        )
        final_key = final_url if deduplicate else key
        final_groups.setdefault(final_key, []).append((discoveries, fetched, failed_fetch))
        final_urls.setdefault(final_key, final_url)

    results: list[EnrichedWebSearchResult] = []
    discarded = 0
    fetched_pages = 0
    for final_key, grouped_discoveries in final_groups.items():
        final_url = final_urls[final_key]
        discoveries = [
            candidate
            for candidates_for_url, _fetched, _failed_fetch in grouped_discoveries
            for candidate in candidates_for_url
        ]
        fetched = next(
            (
                item
                for _candidates_for_url, item, _failed_fetch in grouped_discoveries
                if item is not None and item.error is None
            ),
            None,
        )
        failed_fetch = next(
            (
                item
                for _candidates_for_url, _fetched, item in grouped_discoveries
                if item is not None and item.error
            ),
            None,
        )
        fetch_ok = fetched is not None
        if fetch_ok:
            fetched_pages += 1
        primary = discoveries[0]
        title = primary.title or (fetched.title.strip() if fetched is not None else None)
        if not title:
            discarded += 1
            continue
        content = fetched.content if fetched is not None else ""
        excerpt = _excerpt(content, excerpt_chars) if content else ""
        domain = urlsplit(final_url).hostname or "unknown"
        fetch_error = (
            redact_secret_text(failed_fetch.error) if failed_fetch and failed_fetch.error else None
        )
        results.append(
            EnrichedWebSearchResult(
                result_id=f"R{len(results) + 1}",
                rank=len(results) + 1,
                title=title,
                url=final_url,
                canonical_url=final_url,
                provider_snippet=primary.provider_snippet,
                content_excerpt=(
                    SearchSnippet(text=excerpt, type="extractive", provider=fetched.source)
                    if excerpt and fetched is not None
                    else None
                ),
                content=content[:max_content_chars] if include_content and content else None,
                site_name=primary.site_name,
                site_domain=domain,
                favicon_url=primary.favicon_url,
                discoveries=[item.provenance for item in discoveries],
                fetch_status="success"
                if fetch_ok
                else ("failed" if failed_fetch else "not_requested"),
                fetch_provider=fetched.source if fetched is not None else None,
                fetch_error=fetch_error,
                content_hash=(
                    f"sha256:{hashlib.sha256(content.encode()).hexdigest()}" if content else None
                ),
            )
        )

    synthesis_status: SynthesisStatus = "not_requested"
    answer: EnrichedSynthesisAnswer | None = None
    summary_usage: LLMUsage | None = None
    if profile is not None:
        try:
            synthesis_timeout = endpoint_budget.timeout_for(profile.timeout)
        except TimeoutError:
            # The search/fetch result list remains useful even when the optional
            # stage loses its shared endpoint budget before a model call.
            synthesis_status = "skipped"
        else:
            try:
                synthesized = await synthesize_enriched_results(
                    results,
                    profile_id=synthesis_profile or "",
                    timeout=synthesis_timeout,
                )
            except Exception:
                # Synthesis must never discard otherwise valid retrieval evidence.
                # Do not include provider error text or traceback because an
                # upstream response can contain secret-bearing diagnostics.
                logger.warning("enriched synthesis failed; retrieval results are retained")
                synthesis_status = "failed"
            else:
                if synthesized is None:
                    synthesis_status = "skipped"
                else:
                    results = [
                        result.model_copy(
                            update={"summary": synthesized.summaries.get(result.result_id)}
                        )
                        for result in results
                    ]
                    synthesis_status = "success"
                    answer = synthesized.answer
                    summary_usage = synthesized.usage

    return EnrichedSearchExecution(
        query=query,
        results=results,
        source_outcomes=source_outcomes,
        discarded_candidates=discarded,
        source_attempts=source_attempts,
        visible_search_calls=sum(attempt.visible_search_calls or 0 for attempt in source_attempts),
        provider_metered_search_calls=(
            sum(attempt.provider_metered_search_calls for attempt in source_attempts)
            if source_attempts
            and all(
                attempt.provider_metered_search_calls is not None for attempt in source_attempts
            )
            else None
        ),
        fetched_pages=fetched_pages,
        synthesis_status=synthesis_status,
        answer=answer,
        summary_usage=summary_usage,
    )
