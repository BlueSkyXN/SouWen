"""SouWen Deep Search — search + fetch + two-pass LLM synthesis.

Pipeline:
1. Search via facade → get search results with URLs
2. Extract top-N unique URLs (round-robin across sources)
3. Fetch page content for those URLs
4. Pass 1: Extract query-relevant info from each page (LLM)
5. Pass 2: Synthesize extractions into comprehensive answer (LLM)
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.llm.client import llm_complete
from souwen.llm.models import (
    DeepFetchStats,
    DeepSummaryResult,
    LLMMessage,
    LLMUsage,
    SummaryCitation,
)
from souwen.llm.prompts import (
    format_extractions_for_synthesis,
    get_deep_extract_prompt,
    get_deep_synthesis_prompt,
)
from souwen.models import SearchResponse

logger = logging.getLogger("souwen.llm")

_TRUNCATION_NOTE = "\n\n[Content truncated due to length]"


def _extract_urls_round_robin(
    responses: list[SearchResponse],
    max_urls: int = 5,
) -> list[tuple[str, str, str]]:
    """Extract unique URLs from search results using round-robin across sources.

    Returns list of (url, title, source_name) tuples, deduped by normalized host+path.
    """
    # Collect per-source URL lists
    source_urls: list[list[tuple[str, str, str]]] = []
    for resp in responses:
        items: list[tuple[str, str, str]] = []
        for result in resp.results:
            url = getattr(result, "url", "") or getattr(result, "source_url", "")
            title = getattr(result, "title", "")
            if url:
                items.append((url, title, resp.source.value))
        if items:
            source_urls.append(items)

    if not source_urls:
        return []

    # Round-robin across sources, dedup by normalized URL
    seen: set[str] = set()
    selected: list[tuple[str, str, str]] = []
    max_rounds = max(len(s) for s in source_urls)

    for round_idx in range(max_rounds):
        if len(selected) >= max_urls:
            break
        for source_list in source_urls:
            if round_idx >= len(source_list):
                continue
            url, title, source = source_list[round_idx]
            # Normalize for dedup
            parsed = urlparse(url)
            norm_key = f"{parsed.netloc}{parsed.path}".lower().rstrip("/")
            if norm_key in seen:
                continue
            seen.add(norm_key)
            selected.append((url, title, source))
            if len(selected) >= max_urls:
                break

    return selected


async def deep_summarize(
    query: str,
    *,
    domain: str = "paper",
    sources: list[str] | None = None,
    per_page: int = 10,
    max_fetch: int = 5,
    fetch_provider: str = "builtin",
    fetch_timeout: float = 30.0,
    mode: str = "brief",
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    system_prompt_override: str | None = None,
) -> DeepSummaryResult:
    """Execute deep search: search → fetch → extract → synthesize.

    Args:
        query: User search query.
        domain: Search domain ("paper", "patent", "web").
        sources: Optional source list for search.
        per_page: Results per source.
        max_fetch: Maximum pages to fetch (top N URLs).
        fetch_provider: Fetch provider name.
        fetch_timeout: Per-URL fetch timeout.
        mode: Summary mode.
        model: Optional LLM model override.
        max_tokens: Optional max completion tokens.
        temperature: Optional temperature override.
        system_prompt_override: Custom synthesis prompt override.

    Returns:
        DeepSummaryResult with synthesis, citations, and fetch stats.
    """
    from souwen.facade.search import search
    from souwen.web.fetch import fetch_content

    logger.info("Deep search: query=%r domain=%s max_fetch=%d", query, domain, max_fetch)

    # Step 1: Search
    responses = await search(query, domain=domain, sources=sources, limit=per_page)
    if not responses or not any(r.results for r in responses):
        raise ValueError("No search results found")

    # Step 2: Extract URLs (round-robin across sources)
    url_candidates = _extract_urls_round_robin(responses, max_urls=max_fetch)
    if not url_candidates:
        raise ValueError("No fetchable URLs in search results")

    urls_to_fetch = [u for u, _, _ in url_candidates]
    title_map = {u: t for u, t, _ in url_candidates}
    source_map = {u: s for u, _, s in url_candidates}

    logger.info("Deep search: fetching %d URLs via %s", len(urls_to_fetch), fetch_provider)

    # Step 3: Fetch pages
    fetch_response = await fetch_content(
        urls_to_fetch,
        providers=[fetch_provider],
        timeout=fetch_timeout,
    )

    # Categorize fetch results
    cfg = get_config()
    per_page_chars = (cfg.llm.max_input_tokens * 4) // max(max_fetch, 1)
    fetched_urls: list[str] = []
    failed_urls: list[str] = []
    skipped_urls: list[str] = []
    pages: list[tuple[str, str, str, str]] = []  # (url, title, source, content)

    for result in fetch_response.results:
        if result.error or not result.content:
            failed_urls.append(result.url)
            continue
        fetched_urls.append(result.url)

        content = result.content
        if len(content) > per_page_chars:
            cutoff = max(0, per_page_chars - len(_TRUNCATION_NOTE))
            content = content[:cutoff].rstrip() + _TRUNCATION_NOTE

        # Skip very short content (likely error pages)
        if len(content.split()) < 20:
            skipped_urls.append(result.url)
            continue

        title = result.title or title_map.get(result.url, "")
        source = source_map.get(result.url, result.source)
        pages.append((result.url, title, source, content))

    if not pages:
        raise ValueError("No pages with usable content after fetching")

    total_usage = LLMUsage()
    actual_model = ""

    # Step 4: Pass 1 — Extract query-relevant info from each page
    extract_prompt = get_deep_extract_prompt()
    extractions: list[tuple[int, str, str, str]] = []  # (cid, title, url, extracted_text)
    citations: list[SummaryCitation] = []

    for idx, (url, title, source, content) in enumerate(pages, start=1):
        user_msg = (
            f"User Query: {query}\n\nPage Title: {title}\nURL: {url}\n\nPage Content:\n{content}"
        )
        messages = [
            LLMMessage(role="system", content=extract_prompt),
            LLMMessage(role="user", content=user_msg),
        ]

        try:
            resp = await llm_complete(
                messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            actual_model = resp.model
            total_usage.prompt_tokens += resp.usage.prompt_tokens
            total_usage.completion_tokens += resp.usage.completion_tokens
            total_usage.total_tokens += resp.usage.total_tokens

            extractions.append((idx, title, url, resp.content))
            citations.append(
                SummaryCitation(
                    id=idx,
                    title=title,
                    url=url,
                    source=source,
                )
            )
        except ConfigError:
            raise
        except Exception as exc:
            logger.warning("Deep search extract failed for %s: %s", url, exc)
            # Skip this page but don't fail the whole pipeline

    if not extractions:
        raise ValueError("All page extractions failed")

    # Build used_urls from successful extractions only
    used_urls = [url for _, _, url, _ in extractions]

    # Step 5: Pass 2 — Synthesize across extractions
    synthesis_prompt = get_deep_synthesis_prompt(mode, system_prompt_override)
    formatted = format_extractions_for_synthesis(extractions)

    synthesis_user_msg = (
        f"User Query: {query}\n\n"
        f"Extracted Information from {len(extractions)} Sources:\n\n{formatted}\n\n"
        f"Please synthesize a {mode} answer based on the extracted information above."
    )
    synthesis_messages = [
        LLMMessage(role="system", content=synthesis_prompt),
        LLMMessage(role="user", content=synthesis_user_msg),
    ]

    synthesis_resp = await llm_complete(
        synthesis_messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    total_usage.prompt_tokens += synthesis_resp.usage.prompt_tokens
    total_usage.completion_tokens += synthesis_resp.usage.completion_tokens
    total_usage.total_tokens += synthesis_resp.usage.total_tokens
    actual_model = synthesis_resp.model

    sources_used = len({c.source for c in citations if c.source})

    logger.info(
        "Deep search completed: pages_synthesized=%d sources=%d",
        len(extractions),
        sources_used,
    )

    return DeepSummaryResult(
        query=query,
        summary=synthesis_resp.content,
        mode=mode,
        citations=citations,
        model=actual_model,
        usage=total_usage,
        fetch_stats=DeepFetchStats(
            fetched_urls=fetched_urls,
            failed_urls=failed_urls,
            used_urls=used_urls,
            skipped_urls=skipped_urls,
        ),
        sources_used=sources_used,
        results_used=len(citations),
        pages_synthesized=len(extractions),
    )
