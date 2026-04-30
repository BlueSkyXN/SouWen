"""Tests for souwen.llm.summarize — mock LLM client."""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from souwen.llm.models import LLMResponse, LLMUsage
from souwen.models import Author, PaperResult, SearchResponse, SourceType

summarize_module = importlib.import_module("souwen.llm.summarize")


def _paper(idx: int = 1, abstract: str = "This is a test abstract") -> PaperResult:
    return PaperResult(
        source=SourceType.OPENALEX,
        title=f"Test Paper {idx}",
        authors=[Author(name="John Doe")],
        abstract=abstract,
        doi=f"10.1234/test-{idx}",
        year=2024,
        source_url=f"https://example.com/paper{idx}",
    )


def _response(results: list[PaperResult]) -> SearchResponse:
    return SearchResponse(
        source=SourceType.OPENALEX,
        query="test",
        total_results=len(results),
        results=results,
    )


def _llm_response(content: str = "This is a test summary [1][2].") -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        usage=LLMUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        finish_reason="stop",
    )


def _mock_config(max_input_tokens: int = 6000) -> MagicMock:
    cfg = MagicMock()
    cfg.llm.max_input_tokens = max_input_tokens
    return cfg


async def test_summarize_success():
    mock_llm = AsyncMock(return_value=_llm_response())

    with (
        patch.object(summarize_module, "llm_complete", mock_llm),
        patch.object(summarize_module, "get_config", return_value=_mock_config()),
    ):
        result = await summarize_module.summarize("test query", [_response([_paper(1), _paper(2)])])

    assert result.query == "test query"
    assert result.summary == "This is a test summary [1][2]."
    assert result.mode == "brief"
    assert result.model == "test-model"
    assert result.usage.total_tokens == 150
    assert result.results_used == 2
    assert result.sources_used == 1
    assert [citation.id for citation in result.citations] == [1, 2]
    mock_llm.assert_awaited_once()


async def test_summarize_empty_responses():
    with pytest.raises(ValueError, match="No search results"):
        await summarize_module.summarize("test query", [])


async def test_summarize_all_empty_results():
    with pytest.raises(ValueError, match="No search results"):
        await summarize_module.summarize("test query", [_response([])])


async def test_summarize_truncation():
    long_abstract = "A" * 2000
    mock_llm = AsyncMock(return_value=_llm_response())

    with (
        patch.object(summarize_module, "llm_complete", mock_llm),
        patch.object(
            summarize_module, "get_config", return_value=_mock_config(max_input_tokens=50)
        ),
    ):
        await summarize_module.summarize(
            "test query", [_response([_paper(1, abstract=long_abstract)])]
        )

    messages = mock_llm.await_args.args[0]
    user_message = messages[1].content
    assert "[Results truncated due to length]" in user_message
    assert len(user_message) < 500


async def test_summarize_mode_forwarding():
    mock_llm = AsyncMock(return_value=_llm_response())

    with (
        patch.object(summarize_module, "llm_complete", mock_llm),
        patch.object(summarize_module, "get_config", return_value=_mock_config()),
        patch.object(
            summarize_module, "get_system_prompt", return_value="detailed prompt"
        ) as prompt_mock,
    ):
        result = await summarize_module.summarize(
            "test query", [_response([_paper()])], mode="detailed"
        )

    prompt_mock.assert_called_once_with("detailed", None)
    assert result.mode == "detailed"
    messages = mock_llm.await_args.args[0]
    assert messages[0].content == "detailed prompt"
    assert "Please provide a detailed summary" in messages[1].content


async def test_summarize_custom_prompt():
    mock_llm = AsyncMock(return_value=_llm_response())

    with (
        patch.object(summarize_module, "llm_complete", mock_llm),
        patch.object(summarize_module, "get_config", return_value=_mock_config()),
        patch.object(
            summarize_module, "get_system_prompt", return_value="custom prompt"
        ) as prompt_mock,
    ):
        await summarize_module.summarize(
            "test query",
            [_response([_paper()])],
            system_prompt_override="custom prompt",
        )

    prompt_mock.assert_called_once_with("brief", "custom prompt")
    messages = mock_llm.await_args.args[0]
    assert messages[0].content == "custom prompt"
