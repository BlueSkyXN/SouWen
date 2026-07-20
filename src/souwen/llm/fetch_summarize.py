"""SouWen LLM fetch + summarize — per-URL page content summarization.

Fetches web pages via the souwen fetch subsystem and summarizes each
page's content with the configured LLM.
"""

from __future__ import annotations

import logging
from typing import Literal

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.redaction import redact_secret_text
from souwen.llm.client import LLMError, llm_complete
from souwen.llm.models import LLMMessage, LLMUsage, PageSummaryItem, PageSummaryResult
from souwen.llm.prompts import get_page_summary_prompt

logger = logging.getLogger("souwen.llm")

_TRUNCATION_NOTE = "\n\n[Content truncated due to length]"


def _normalize_string_list_arg(value: object, *, name: str) -> list[str]:
    """Normalize public string-or-sequence arguments into a clean string list."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list | tuple):
        items = list(value)
    else:
        raise ValueError(f"{name} 必须是字符串或字符串列表")

    normalized: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{name} 必须是非空字符串或非空字符串列表")
        normalized.append(item.strip())
    return normalized


async def summarize_pages(
    urls: list[str] | str,
    *,
    provider: str = "builtin",
    providers: list[str] | str | None = None,
    strategy: Literal["fallback", "fanout"] = "fallback",
    timeout: float = 30.0,
    mode: str = "brief",
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    system_prompt_override: str | None = None,
) -> PageSummaryResult:
    """Fetch URLs and summarize each page's content with LLM.

    Args:
        urls: URL or URL list to fetch and summarize.
        provider: Backward-compatible single fetch provider name.
        providers: Optional fetch provider or provider list. Takes precedence over provider.
        strategy: Multi-provider fetch strategy, "fallback" or "fanout".
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

    normalized_urls = _normalize_string_list_arg(urls, name="urls")
    if not normalized_urls:
        return PageSummaryResult(total_urls=0)

    selected_providers = _normalize_string_list_arg(providers, name="providers")
    if not selected_providers:
        selected_providers = _normalize_string_list_arg(provider, name="provider")
    logger.info(
        "Fetch+Summarize: fetching %d URLs via %s strategy=%s",
        len(normalized_urls),
        selected_providers,
        strategy,
    )
    fetch_response = await fetch_content(
        normalized_urls,
        providers=selected_providers,
        strategy=strategy,
        timeout=timeout,
    )

    cfg = get_config()
    max_input_chars = cfg.llm.max_input_tokens * 4
    system_prompt = get_page_summary_prompt(mode, system_prompt_override)
    total_usage = LLMUsage()
    items: list[PageSummaryItem] = []
    actual_model = ""

    for result in fetch_response.results:
        # Failed fetch
        if result.error or not result.content:
            items.append(
                PageSummaryItem(
                    url=result.url,
                    final_url=result.final_url,
                    title=result.title,
                    error=result.error or "Empty content",
                    provider=result.source,
                )
            )
            continue

        # word_count reflects the fetched content before this LLM-specific truncation.
        word_count = len(result.content.split())

        # Truncate long content
        content = result.content
        truncated = result.content_truncated
        if len(content) > max_input_chars:
            cutoff = max(0, max_input_chars - len(_TRUNCATION_NOTE))
            content = content[:cutoff].rstrip() + _TRUNCATION_NOTE
            truncated = True

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
                messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            actual_model = llm_response.model
            # Accumulate usage
            total_usage.prompt_tokens += llm_response.usage.prompt_tokens
            total_usage.completion_tokens += llm_response.usage.completion_tokens
            total_usage.total_tokens += llm_response.usage.total_tokens

            items.append(
                PageSummaryItem(
                    url=result.url,
                    final_url=result.final_url,
                    title=result.title,
                    summary=llm_response.content,
                    word_count=word_count,
                    content_truncated=truncated,
                    provider=result.source,
                )
            )
        except (ConfigError, LLMError):
            raise
        except Exception as exc:
            safe_error = redact_secret_text(str(exc)) or "unknown error"
            items.append(
                PageSummaryItem(
                    url=result.url,
                    final_url=result.final_url,
                    title=result.title,
                    word_count=word_count,
                    content_truncated=truncated,
                    error=f"LLM error: {safe_error}",
                    provider=result.source,
                )
            )

    ok_count = sum(1 for item in items if item.error is None)
    failed_count = len(items) - ok_count

    logger.info(
        "Fetch+Summarize completed: total=%d ok=%d failed=%d",
        len(items),
        ok_count,
        failed_count,
    )

    return PageSummaryResult(
        items=items,
        mode=mode,
        model=actual_model,
        usage=total_usage,
        total_urls=len(normalized_urls),
        total_ok=ok_count,
        total_failed=failed_count,
    )
