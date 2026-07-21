"""Search-to-fetch enrichment without changing the legacy ``web_search`` response contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from souwen.models import (
    EnrichedWebSearchResult,
    FetchResult,
    SearchCandidate,
    SearchSnippet,
    SearchSourceProvenance,
)
from souwen.web.fetch import fetch_content
from souwen.web.search import web_search

SourceOutcome = Literal["success_with_results", "success_empty", "timeout", "failed"]


@dataclass(frozen=True, slots=True)
class EnrichedSearchExecution:
    """Python-level result for the additive enrichment service; REST is added later."""

    query: str
    results: list[EnrichedWebSearchResult]
    source_outcomes: dict[str, SourceOutcome]
    discarded_candidates: int


def _canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, "")
    )


def _excerpt(content: str, limit: int) -> str:
    content = " ".join(content.split())
    return content[:limit].rstrip()


def _candidate_from_result(result) -> SearchCandidate:
    snippet = result.snippet.strip()
    return SearchCandidate(
        title=result.title,
        url=result.url,
        provider_snippet=(
            SearchSnippet(text=snippet, type="provider_snippet", provider=result.source)
            if snippet
            else None
        ),
        provenance=SearchSourceProvenance(
            source_id=result.source,
            scheme_id="registry_adapter",
            requested_model_id=None,
        ),
    )


async def enriched_web_search(
    query: str,
    engines: list[str] | str | None = None,
    *,
    max_results_per_engine: int = 10,
    fetch: bool = True,
    fetch_providers: list[str] | str | None = None,
    max_pages: int = 5,
    fetch_timeout: float = 30.0,
    include_content: bool = False,
    max_content_chars: int = 4_000,
    excerpt_chars: int = 500,
) -> EnrichedSearchExecution:
    """Return title/URL-gated results enriched by the existing SSRF-safe fetch pipeline."""
    if not 1 <= max_pages <= 100:
        raise ValueError("max_pages 必须在 1..100 范围内")
    if max_content_chars < 1 or excerpt_chars < 1:
        raise ValueError("content/excerpt 长度必须为正数")

    response = await web_search(
        query,
        engines=engines,
        max_results_per_engine=max_results_per_engine,
        deduplicate=False,
    )
    candidates = [_candidate_from_result(result) for result in response.results]
    source_outcomes: dict[str, SourceOutcome] = {}
    for candidate in candidates:
        source_outcomes[candidate.provenance.source_id] = "success_with_results"
    if engines is not None:
        requested = [engines] if isinstance(engines, str) else engines
        for source_id in requested:
            source_outcomes.setdefault(source_id, "success_empty")

    grouped: dict[str, list[SearchCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(_canonical_url(candidate.url), []).append(candidate)

    fetch_by_url: dict[str, FetchResult] = {}
    if fetch and grouped:
        urls = list(grouped)[:max_pages]
        fetched = await fetch_content(
            urls,
            providers=fetch_providers,
            strategy="fallback",
            timeout=fetch_timeout,
            max_length=max_content_chars,
        )
        fetch_by_url = {_canonical_url(item.url): item for item in fetched.results}

    results: list[EnrichedWebSearchResult] = []
    discarded = 0
    for canonical_url, discoveries in grouped.items():
        primary = discoveries[0]
        fetched = fetch_by_url.get(canonical_url)
        fetch_ok = fetched is not None and fetched.error is None
        title = primary.title or (fetched.title.strip() if fetch_ok else None)
        if not title:
            discarded += 1
            continue
        final_url = _canonical_url(fetched.final_url) if fetch_ok else canonical_url
        content = fetched.content if fetch_ok else ""
        excerpt = _excerpt(content, excerpt_chars) if content else ""
        domain = urlsplit(final_url).hostname or "unknown"
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
                fetch_status="success" if fetch_ok else ("failed" if fetched else "not_requested"),
                fetch_provider=fetched.source if fetch_ok and fetched else None,
                fetch_error=fetched.error if fetched and fetched.error else None,
                content_hash=(
                    f"sha256:{hashlib.sha256(content.encode()).hexdigest()}" if content else None
                ),
            )
        )
    return EnrichedSearchExecution(query, results, source_outcomes, discarded)
