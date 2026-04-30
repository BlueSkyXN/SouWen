"""OpenAI Chat Completions protocol provider."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from souwen.core.exceptions import RateLimitError
from souwen.llm.client import LLMError, _LLMRetriableError
from souwen.llm.models import LLMMessage, LLMResponse, LLMUsage

logger = logging.getLogger("souwen.llm")


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
    """Complete a conversation through OpenAI Chat Completions."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    wire_messages: list[dict[str, str]] = []
    if system is not None:
        wire_messages.append({"role": "system", "content": system})
    wire_messages.extend({"role": m.role, "content": m.content} for m in messages)

    payload: dict[str, Any] = {
        "model": model,
        "messages": wire_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
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

    logger.debug("Calling OpenAI Chat Completions provider: %s", url)
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

    choices = data.get("choices", [])
    if not choices:
        raise LLMError("LLM response contained no choices")

    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content", "")
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise LLMError("LLM response message content is not text")

    usage_data = data.get("usage", {})
    usage = LLMUsage(
        prompt_tokens=usage_data.get("prompt_tokens", 0),
        completion_tokens=usage_data.get("completion_tokens", 0),
        total_tokens=usage_data.get("total_tokens", 0),
    )

    return LLMResponse(
        content=content,
        model=data.get("model", model),
        usage=usage,
        finish_reason=choice.get("finish_reason", "") or "",
    )
