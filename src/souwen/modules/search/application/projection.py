"""Compact Search projections shared by the MCP, HTTP, and Python entries.

SPEC 2.3: callers see numbered title/URL/snippet items (papers add year and
authors), a trailing line naming the sources that produced results, and one
actionable sentence when everything failed. Provenance arrays, request context,
and identifiers stay internal.
"""

from __future__ import annotations

from dataclasses import dataclass

from souwen.platform.provider_spi import (
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    SearchPage,
)

_MAX_AUTHORS = 3
_SNIPPET_CHARS = 400


@dataclass(frozen=True, slots=True)
class CompactSearchItem:
    """One flat search result; ``year``/``authors`` exist only when known."""

    title: str
    url: str | None
    snippet: str | None
    year: int | None = None
    authors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompactSearchSummary:
    """Flat search outcome plus the sources that actually produced items."""

    results: tuple[CompactSearchItem, ...]
    sources: tuple[str, ...]
    partial: bool = False


def project_search_page(page: SearchPage) -> CompactSearchSummary:
    """Flatten one canonical SearchPage into the compact item projection."""

    items = tuple(
        CompactSearchItem(
            title=item.title,
            url=str(item.url) if item.url is not None else None,
            snippet=(item.snippet or "").strip() or None,
            year=item.attributes.year if item.attributes is not None else None,
            authors=item.attributes.authors if item.attributes is not None else (),
        )
        for item in page.items
    )
    return CompactSearchSummary(
        results=items,
        sources=tuple(page.meta.succeeded),
        partial=page.meta.partial,
    )


def format_search_summary(summary: CompactSearchSummary) -> str:
    """Render the compact multi-line text MCP and CLI return for ``search``."""

    if not summary.results:
        return "No results. Try a broader query or another domain."
    lines: list[str] = []
    for index, item in enumerate(summary.results, start=1):
        heading = item.title
        if item.year is not None:
            heading = f"{heading} ({item.year})"
        if item.authors:
            shown = ", ".join(item.authors[:_MAX_AUTHORS])
            more = len(item.authors) - _MAX_AUTHORS
            heading = f"{heading} — {shown}" + (f" +{more}" if more > 0 else "")
        lines.append(f"{index}. {heading}")
        if item.url is not None:
            lines.append(f"   {item.url}")
        if item.snippet is not None:
            snippet = item.snippet[:_SNIPPET_CHARS]
            lines.append(f"   {snippet}")
    sources_line = "results from: " + (", ".join(summary.sources) or "none")
    if summary.partial:
        sources_line += " (partial: some sources failed)"
    lines.append(sources_line)
    return "\n".join(lines)


_RECOVERY_HINT = {
    ProviderErrorCode.RATE_LIMITED: "wait a moment and retry",
    ProviderErrorCode.DEADLINE_EXCEEDED: "retry with a narrower query or fewer sources",
    ProviderErrorCode.INVALID_REQUEST: "check the query and domain arguments",
    ProviderErrorCode.POLICY_BLOCKED: "the request is blocked by policy; adjust the query",
}


def format_search_error(error: ProviderError) -> str:
    """One actionable sentence naming every tried source and failure class."""

    failures = getattr(error, "failures", ())
    if failures:
        tried = ", ".join(f"{failure.provider}: {failure.code}" for failure in failures)
    elif error.provider_id is not None:
        tried = f"{error.provider_id}: {error.code.value}"
    else:
        tried = error.code.value
    hint = _RECOVERY_HINT.get(error.code, "retry later or pick sources explicitly")
    return f"Search failed on every candidate ({tried}). To proceed: {hint}."


def format_search_error_from_failures(
    failures: tuple[ProviderFailure, ...],
) -> str:
    """Same actionable sentence built directly from canonical failures."""

    tried = ", ".join(f"{failure.provider}: {failure.code}" for failure in failures)
    return f"Search failed on every candidate ({tried}). To proceed: retry later or pick sources explicitly."


__all__ = [
    "CompactSearchItem",
    "CompactSearchSummary",
    "format_search_error",
    "format_search_error_from_failures",
    "format_search_summary",
    "project_search_page",
]
