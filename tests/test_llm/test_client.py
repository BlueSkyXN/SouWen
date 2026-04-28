"""Tests for souwen.llm.client — mock httpx, no real API calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from souwen.core.exceptions import ConfigError, RateLimitError
from souwen.llm import client as llm_client
from souwen.llm.client import LLMError, _LLMRetriableError, llm_complete
from souwen.llm.models import LLMMessage


@pytest.fixture
def mock_llm_config():
    mock_cfg = MagicMock()
    mock_cfg.llm.enabled = True
    mock_cfg.llm.get_api_key.return_value = "test-key-123"
    mock_cfg.llm.api_key = "test-key"
    mock_cfg.llm.api_keys = []
    mock_cfg.llm.base_url = "https://api.test.com/v1"
    mock_cfg.llm.model = "test-model"
    mock_cfg.llm.max_tokens = 100
    mock_cfg.llm.temperature = 0.5
    mock_cfg.llm.timeout = 30
    mock_cfg.get_proxy.return_value = None
    with patch("souwen.llm.client.get_config", return_value=mock_cfg):
        yield mock_cfg


def _mock_response(status_code: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.headers = {}
    mock_response.text = text
    if json_data is not None:
        mock_response.json.return_value = json_data
    return mock_response


def _mock_async_client(response: MagicMock) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.post.return_value = response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def _call_without_retry(messages: list[LLMMessage]):
    return await llm_client.llm_complete.__wrapped__(messages)


async def test_llm_complete_success(mock_llm_config):
    mock_response = _mock_response(
        200,
        {
            "choices": [{"message": {"content": "test summary"}, "finish_reason": "stop"}],
            "model": "test-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        },
    )
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.client.httpx.AsyncClient", return_value=mock_client) as async_client:
        result = await llm_complete([LLMMessage(role="user", content="Summarize this")])

    assert result.content == "test summary"
    assert result.model == "test-model"
    assert result.finish_reason == "stop"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 20
    assert result.usage.total_tokens == 30
    async_client.assert_called_once()
    mock_client.post.assert_awaited_once()
    _, kwargs = mock_client.post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer test-key-123"
    assert kwargs["json"]["model"] == "test-model"
    assert kwargs["json"]["max_tokens"] == 100
    assert kwargs["json"]["temperature"] == 0.5


async def test_llm_complete_not_enabled(mock_llm_config):
    mock_llm_config.llm.enabled = False

    with pytest.raises(ConfigError):
        await _call_without_retry([LLMMessage(role="user", content="test")])


async def test_llm_complete_no_api_key(mock_llm_config):
    mock_llm_config.llm.api_key = None
    mock_llm_config.llm.api_keys = []
    mock_llm_config.llm.get_api_key.return_value = None

    with pytest.raises(ConfigError):
        await _call_without_retry([LLMMessage(role="user", content="test")])


async def test_llm_complete_429(mock_llm_config):
    mock_response = _mock_response(429, text="rate limited")
    mock_response.headers = {"retry-after": "7"}
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(RateLimitError) as exc_info:
            await _call_without_retry([LLMMessage(role="user", content="test")])

    assert exc_info.value.retry_after == 7.0


async def test_llm_complete_500(mock_llm_config):
    mock_response = _mock_response(500, text="server error")
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(_LLMRetriableError) as exc_info:
            await _call_without_retry([LLMMessage(role="user", content="test")])

    assert exc_info.value.status_code == 500
    assert exc_info.value.body == "server error"


async def test_llm_complete_400(mock_llm_config):
    mock_response = _mock_response(400, text="bad request")
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(LLMError) as exc_info:
            await _call_without_retry([LLMMessage(role="user", content="test")])

    assert exc_info.value.status_code == 400
    assert exc_info.value.body == "bad request"


async def test_llm_complete_empty_choices(mock_llm_config):
    mock_response = _mock_response(200, {"choices": [], "model": "test-model"})
    mock_client = _mock_async_client(mock_response)

    with patch("souwen.llm.client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(LLMError, match="空 choices"):
            await _call_without_retry([LLMMessage(role="user", content="test")])
