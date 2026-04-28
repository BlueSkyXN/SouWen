"""SouWen LLM summarization orchestrator.

Coordinates prompt construction, search-result formatting, LLM completion, and
summary metadata assembly for search responses.
"""

from __future__ import annotations

import logging

from souwen.config import get_config
from souwen.llm.client import llm_complete
from souwen.llm.models import LLMMessage, SummaryResult
from souwen.llm.prompts import format_results_for_llm, get_system_prompt
from souwen.models import SearchResponse

logger = logging.getLogger("souwen.llm")

_TRUNCATION_NOTE = "\n\n[Results truncated due to length]"


async def summarize(
    query: str,
    responses: list[SearchResponse],
    *,
    mode: str = "brief",
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    system_prompt_override: str | None = None,
    max_results: int = 20,
) -> SummaryResult:
    """Summarize search results with the configured LLM.

    Args:
        query: Original user query.
        responses: Search responses to summarize.
        mode: Summary mode; caller is responsible for valid values.
        model: Optional model override for the LLM client.
        max_tokens: Optional completion token limit override.
        temperature: Optional temperature override.
        system_prompt_override: Optional custom system prompt.
        max_results: Maximum formatted results to include.

    Returns:
        Summary result containing generated text, citations, and usage metadata.

    Raises:
        ValueError: If there are no usable search results.
        LLMError: Propagated from the LLM client.
        ConfigError: Propagated from configuration access or the LLM client.
    """
    if not responses or not any(response.results for response in responses):
        raise ValueError("No search results to summarize")

    logger.info(
        "Summarizing search results: query=%r mode=%s responses=%d max_results=%d",
        query,
        mode,
        len(responses),
        max_results,
    )

    formatted_text, citations = format_results_for_llm(
        responses,
        max_results=max_results,
    )
    if not citations:
        raise ValueError("No search results to summarize")

    cfg = get_config()
    max_input_chars = cfg.llm.max_input_tokens * 4
    if len(formatted_text) > max_input_chars:
        logger.warning(
            "Truncating formatted search results from %d to %d characters",
            len(formatted_text),
            max_input_chars,
        )
        cutoff = max(0, max_input_chars - len(_TRUNCATION_NOTE))
        formatted_text = formatted_text[:cutoff].rstrip() + _TRUNCATION_NOTE

    system_prompt = get_system_prompt(mode, system_prompt_override)
    user_prompt = (
        f"Query: {query}\n\n"
        f"Search Results:\n\n{formatted_text}\n\n"
        f"Please provide a {mode} summary of these search results."
    )
    messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=user_prompt),
    ]

    logger.debug(
        "Calling LLM for summary: mode=%s model=%s citations=%d",
        mode,
        model or "<config-default>",
        len(citations),
    )
    llm_response = await llm_complete(
        messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    source_count = len({citation.source for citation in citations if citation.source})
    logger.info(
        "LLM summary completed: model=%s sources_used=%d results_used=%d",
        llm_response.model,
        source_count,
        len(citations),
    )

    return SummaryResult(
        query=query,
        summary=llm_response.content,
        mode=mode,
        citations=citations,
        model=llm_response.model,
        usage=llm_response.usage,
        sources_used=source_count,
        results_used=len(citations),
    )
