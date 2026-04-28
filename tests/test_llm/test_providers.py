"""Tests for LLM providers — OpenAI Chat, OpenAI Responses, Anthropic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from souwen.core.exceptions import RateLimitError
from souwen.llm.client import LLMError, _LLMRetriableError
from souwen.llm.models import LLMMessage, LLMResponse
from souwen.llm.providers import anthropic_messages, openai_chat, openai_responses


# Shared helpers
def _mock_response(status_code, json_data=None, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.headers = {}
    r.text = text
    if json_data is not None:
        r.json.return_value = json_data
    return r


def _mock_async_client(response):
    c = AsyncMock()
    c.post.return_value = response
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=False)
    return c


_COMMON_KWARGS = dict(
    api_key="test-key",
    base_url="https://api.test.com/v1",
    model="test-model",
    max_tokens=100,
    temperature=0.5,
    timeout=30,
)
_ANTHROPIC_PATCH = "souwen.llm.providers.anthropic_messages.httpx.AsyncClient"


def _messages() -> list[LLMMessage]:
    return [LLMMessage(role="user", content="Hello")]


async def test_openai_chat_success():
    mock_response = _mock_response(
        200,
        {
            "choices": [{"message": {"content": "Hello back"}, "finish_reason": "stop"}],
            "model": "test-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        },
    )
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.providers.openai_chat.httpx.AsyncClient", return_value=mock_client):
        result = await openai_chat.complete(None, _messages(), **_COMMON_KWARGS)

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello back"
    assert result.model == "test-model"
    assert result.finish_reason == "stop"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 20
    assert result.usage.total_tokens == 30
    mock_client.post.assert_awaited_once()


async def test_openai_chat_with_system():
    mock_response = _mock_response(
        200,
        {
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "model": "test-model",
        },
    )
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.providers.openai_chat.httpx.AsyncClient", return_value=mock_client):
        await openai_chat.complete("You are helpful", _messages(), **_COMMON_KWARGS)

    _, kwargs = mock_client.post.call_args
    payload = kwargs["json"]
    assert payload["messages"][0] == {"role": "system", "content": "You are helpful"}
    assert payload["messages"][1] == {"role": "user", "content": "Hello"}


async def test_openai_chat_429():
    mock_response = _mock_response(429, text="rate limited")
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.providers.openai_chat.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(RateLimitError):
            await openai_chat.complete(None, _messages(), **_COMMON_KWARGS)


async def test_openai_chat_empty_choices():
    mock_response = _mock_response(200, {"choices": [], "model": "test-model"})
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.providers.openai_chat.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(LLMError, match="no choices"):
            await openai_chat.complete(None, _messages(), **_COMMON_KWARGS)


async def test_openai_responses_success():
    mock_response = _mock_response(
        200,
        {
            "id": "resp_test",
            "model": "test-model",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Hello world"}],
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        },
    )
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.providers.openai_responses.httpx.AsyncClient", return_value=mock_client):
        result = await openai_responses.complete(None, _messages(), **_COMMON_KWARGS)

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello world"
    assert result.model == "test-model"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 20
    assert result.usage.total_tokens == 30


async def test_openai_responses_with_instructions():
    mock_response = _mock_response(
        200,
        {
            "model": "test-model",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}],
        },
    )
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.providers.openai_responses.httpx.AsyncClient", return_value=mock_client):
        await openai_responses.complete("Follow instructions", _messages(), **_COMMON_KWARGS)

    _, kwargs = mock_client.post.call_args
    payload = kwargs["json"]
    assert payload["instructions"] == "Follow instructions"


async def test_openai_responses_multi_text_blocks():
    mock_response = _mock_response(
        200,
        {
            "model": "test-model",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Part 1"},
                        {"type": "output_text", "text": "Part 2"},
                    ],
                }
            ],
        },
    )
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.providers.openai_responses.httpx.AsyncClient", return_value=mock_client):
        result = await openai_responses.complete(None, _messages(), **_COMMON_KWARGS)

    assert result.content == "Part 1\nPart 2"


async def test_openai_responses_no_text_blocks():
    mock_response = _mock_response(
        200,
        {
            "model": "test-model",
            "output": [
                {"type": "message", "content": [{"type": "image", "url": "x"}]},
            ],
        },
    )
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.providers.openai_responses.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(LLMError, match="No text content"):
            await openai_responses.complete(None, _messages(), **_COMMON_KWARGS)


async def test_anthropic_messages_success():
    mock_response = _mock_response(
        200,
        {
            "id": "msg_test",
            "model": "claude-test",
            "content": [{"type": "text", "text": "Claude response"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 15, "output_tokens": 25},
        },
    )
    mock_client = _mock_async_client(mock_response)

    with patch(_ANTHROPIC_PATCH, return_value=mock_client):
        result = await anthropic_messages.complete(None, _messages(), **_COMMON_KWARGS)

    assert isinstance(result, LLMResponse)
    assert result.content == "Claude response"
    assert result.model == "claude-test"
    assert result.finish_reason == "end_turn"
    assert result.usage.prompt_tokens == 15
    assert result.usage.completion_tokens == 25
    assert result.usage.total_tokens == 40


async def test_anthropic_messages_auth_headers():
    mock_response = _mock_response(
        200,
        {"model": "claude-test", "content": [{"type": "text", "text": "OK"}], "usage": {}},
    )
    mock_client = _mock_async_client(mock_response)

    with patch(_ANTHROPIC_PATCH, return_value=mock_client):
        await anthropic_messages.complete(None, _messages(), **_COMMON_KWARGS)

    _, kwargs = mock_client.post.call_args
    headers = kwargs["headers"]
    assert headers["x-api-key"] == "test-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in headers


async def test_anthropic_messages_system_prompt():
    mock_response = _mock_response(
        200,
        {"model": "claude-test", "content": [{"type": "text", "text": "OK"}], "usage": {}},
    )
    mock_client = _mock_async_client(mock_response)

    with patch(_ANTHROPIC_PATCH, return_value=mock_client):
        await anthropic_messages.complete("Claude system", _messages(), **_COMMON_KWARGS)

    _, kwargs = mock_client.post.call_args
    payload = kwargs["json"]
    assert payload["system"] == "Claude system"
    assert payload["messages"] == [{"role": "user", "content": "Hello"}]


async def test_anthropic_messages_multi_blocks():
    mock_response = _mock_response(
        200,
        {
            "model": "claude-test",
            "content": [{"type": "text", "text": "Part 1"}, {"type": "text", "text": "Part 2"}],
            "usage": {},
        },
    )
    mock_client = _mock_async_client(mock_response)

    with patch(_ANTHROPIC_PATCH, return_value=mock_client):
        result = await anthropic_messages.complete(None, _messages(), **_COMMON_KWARGS)

    assert result.content == "Part 1\nPart 2"


async def test_anthropic_messages_500():
    mock_response = _mock_response(500, text="server error")
    mock_client = _mock_async_client(mock_response)

    with patch(_ANTHROPIC_PATCH, return_value=mock_client):
        with pytest.raises(_LLMRetriableError) as exc_info:
            await anthropic_messages.complete(None, _messages(), **_COMMON_KWARGS)

    assert exc_info.value.status_code == 500
    assert exc_info.value.body == "server error"
