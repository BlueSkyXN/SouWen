"""SouWen LLM fetch + summarize — per-URL page content summarization.

Fetches web pages via the souwen fetch subsystem and summarizes each
page's content with the configured LLM.
"""

from __future__ import annotations

import logging

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.llm.client import llm_complete
from souwen.llm.models import LLMMessage, LLMUsage, PageSummaryItem, PageSummaryResult
from souwen.llm.prompts import get_page_summary_prompt

logger = logging.getLogger("souwen.llm")

_TRUNCATION_NOTE = "\n\n[Content truncated due to length]"


async def summarize_pages(
    urls: list[str],
    *,
    provider: str = "builtin",
    timeout: float = 30.0,
    mode: str = "brief",
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    system_prompt_override: str | None = None,
) -> PageSummaryResult:
    """Fetch URLs and summarize each page's content with LLM.

    Args:
        urls: List of URLs to fetch and summarize.
        provider: Fetch provider name (e.g. "builtin", "jina_reader").
        timeout: Per-URL fetch timeout in seconds.
        mode: Summary mode ("brief", "detailed", "academic").
        model: Optional LLM model override.
        max_tokens: Optional max completion tokens.
        temperature: Optional temperature override.
        system_prompt_override: Optional custom system prompt.

    Returns:
        PageSummaryResult with per-URL summary items.
    """
    from souwen.web.fetch import fetch_content

    if not urls:
        return PageSummaryResult(total_urls=0)

    logger.info("Fetch+Summarize: fetching %d URLs via %s", len(urls), provider)
    fetch_response = await fetch_content(urls, providers=[provider], timeout=timeout)

    cfg = get_config()
    max_input_chars = cfg.llm.max_input_tokens * 4
    system_prompt = get_page_summary_prompt(mode, system_prompt_override)
    total_usage = LLMUsage()
    items: list[PageSummaryItem] = []
    actual_model = ""

    for result in fetch_response.results:
        # Failed fetch
        if result.error or not result.content:
            items.append(PageSummaryItem(
                url=result.url,
                final_url=result.final_url,
                title=result.title,
                error=result.error or "Empty content",
                provider=result.source,
            ))
            continue

        # Truncate long content
        content = result.content
        truncated = result.content_truncated
        if len(content) > max_input_chars:
            cutoff = max(0, max_input_chars - len(_TRUNCATION_NOTE))
            content = content[:cutoff].rstrip() + _TRUNCATION_NOTE
            truncated = True

        word_count = len(content.split())

        # Build messages
        user_prompt = (
            f"Page Title: {result.title}\n"
            f"URL: {result.final_url or result.url}\n\n"
            f"Page Content:\n{content}"
        )
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        try:
            llm_response = await llm_complete(
                messages, model=model, max_tokens=max_tokens, temperature=temperature,
            )
            actual_model = llm_response.model
            # Accumulate usage
            total_usage.prompt_tokens += llm_response.usage.prompt_tokens
            total_usage.completion_tokens += llm_response.usage.completion_tokens
            total_usage.total_tokens += llm_response.usage.total_tokens

            items.append(PageSummaryItem(
                url=result.url,
                final_url=result.final_url,
                title=result.title,
                summary=llm_response.content,
                word_count=word_count,
                content_truncated=truncated,
                provider=result.source,
            ))
        except ConfigError:
            raise
        except Exception as exc:
            logger.warning("LLM summarize failed for %s: %s", result.url, exc)
            items.append(PageSummaryItem(
                url=result.url,
                final_url=result.final_url,
                title=result.title,
                word_count=word_count,
                content_truncated=truncated,
                error=f"LLM error: {exc}",
                provider=result.source,
            ))

    ok_count = sum(1 for item in items if item.error is None)
    failed_count = len(items) - ok_count

    logger.info(
        "Fetch+Summarize completed: total=%d ok=%d failed=%d",
        len(items), ok_count, failed_count,
    )

    return PageSummaryResult(
        items=items,
        mode=mode,
        model=actual_model,
        usage=total_usage,
        total_urls=len(urls),
        total_ok=ok_count,
        total_failed=failed_count,
    )
