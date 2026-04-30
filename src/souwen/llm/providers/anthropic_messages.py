"""Anthropic Claude Messages API protocol provider."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from souwen.core.exceptions import RateLimitError
from souwen.llm.client import LLMError, _LLMRetriableError
from souwen.llm.models import LLMMessage, LLMResponse, LLMUsage

logger = logging.getLogger("souwen.llm")


def _extract_text_blocks(blocks: list) -> str:
    """Extract and concatenate all text blocks from response content."""
    texts = []
    for block in blocks:
        if isinstance(block, dict):
            if block.get("type") in ("text", "output_text"):
                texts.append(block.get("text", ""))
            elif "text" in block and block.get("type") not in (
                "image",
                "tool_use",
                "tool_result",
            ):
                texts.append(block["text"])
    if not texts:
        raise LLMError("No text content in LLM response")
    return "\n".join(texts)


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code == 429:
        retry_after = None
        h = resp.headers.get("retry-after")
        if h:
            try:
                retry_after = float(h)
            except ValueError:
                pass
        raise RateLimitError("LLM API rate limited (429)", retry_after=retry_after)

    if resp.status_code >= 500:
        body = resp.text[:500]
        raise _LLMRetriableError(
            f"LLM upstream error: HTTP {resp.status_code}",
            status_code=resp.status_code,
            body=body,
        )

    if resp.status_code != 200:
        body = resp.text[:500]
        raise LLMError(
            f"LLM API error: HTTP {resp.status_code} - {body}",
            status_code=resp.status_code,
            body=body,
        )


async def complete(
    system: str | None,
    messages: list[LLMMessage],
    *,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int,
    temperature: float,
    timeout: float,
    proxy: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> LLMResponse:
    """Complete a conversation through Anthropic Claude Messages."""
    url = f"{base_url.rstrip('/')}/messages"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens,
    }
    if system is not None:
        payload["system"] = system
    if temperature is not None:
        payload["temperature"] = temperature

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    client_kwargs: dict[str, Any] = {
        "timeout": httpx.Timeout(timeout, connect=10.0),
        "follow_redirects": True,
    }
    if proxy:
        client_kwargs["proxy"] = proxy

    logger.debug("Calling Anthropic Messages provider: %s", url)
    async with httpx.AsyncClient(**client_kwargs) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise _LLMRetriableError(f"LLM HTTP request failed: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"HTTP request failed: {exc}", status_code=None) from exc

    _raise_for_status(resp)

    try:
        data = resp.json()
    except Exception as exc:
        raise LLMError(f"Failed to parse LLM response: {exc}") from exc

    blocks = data.get("content", [])
    if not isinstance(blocks, list):
        raise LLMError("LLM response content is not a block list")
    content = _extract_text_blocks(blocks)

    usage_data = data.get("usage", {})
    prompt_tokens = usage_data.get("input_tokens", 0)
    completion_tokens = usage_data.get("output_tokens", 0)
    usage = LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )

    return LLMResponse(
        content=content,
        model=data.get("model", model),
        usage=usage,
        finish_reason=data.get("stop_reason", "") or "",
    )
