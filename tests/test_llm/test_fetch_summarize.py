"""Tests for souwen.llm.fetch_summarize module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from souwen.llm.models import LLMResponse, LLMUsage
from souwen.models import FetchResponse, FetchResult


# ── Helpers ──────────────────────────────────────────────


def _make_fetch_result(
    url: str,
    content: str = "Some page content here with enough words",
    error: str | None = None,
    title: str = "Test Page",
) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        title=title,
        content=content,
        error=error,
        source="builtin",
    )


def _make_fetch_response(results: list[FetchResult]) -> FetchResponse:
    ok = sum(1 for r in results if r.error is None and r.content)
    return FetchResponse(
        urls=[r.url for r in results],
        results=results,
        total=len(results),
        total_ok=ok,
        total_failed=len(results) - ok,
        provider="builtin",
    )


def _make_llm_response(text: str = "Summary text") -> LLMResponse:
    return LLMResponse(
        content=text,
        model="test-model",
        usage=LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )


def _mock_config(max_input_tokens: int = 6000) -> MagicMock:
    cfg = MagicMock()
    cfg.llm.enabled = True
    cfg.llm.max_input_tokens = max_input_tokens
    cfg.llm.api_key = "test-key"
    cfg.llm.api_keys = []
    cfg.llm.base_url = "https://api.openai.com/v1"
    cfg.llm.model = "gpt-4o-mini"
    cfg.llm.max_tokens = 2048
    cfg.llm.temperature = 0.3
    cfg.llm.protocol = "openai_chat"
    cfg.llm.anthropic_version = "2023-06-01"
    return cfg


# ── fetch_summarize tests ────────────────────────────────


class TestSummarizePages:
    @pytest.fixture(autouse=True)
    def _mock_deps(self):
        with (
            patch("souwen.web.fetch.fetch_content", new_callable=AsyncMock) as self.mock_fetch,
            patch(
                "souwen.llm.fetch_summarize.llm_complete", new_callable=AsyncMock
            ) as self.mock_llm,
            patch("souwen.llm.fetch_summarize.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = _mock_config()
            yield

    async def test_empty_urls(self):
        from souwen.llm.fetch_summarize import summarize_pages

        result = await summarize_pages([])

        assert result.total_urls == 0
        assert result.items == []
        self.mock_fetch.assert_not_awaited()
        self.mock_llm.assert_not_awaited()

    async def test_success_single_url(self):
        from souwen.llm.fetch_summarize import summarize_pages

        fr = _make_fetch_result(
            "https://example.com",
            content="This is a test page with enough content to process",
        )
        self.mock_fetch.return_value = _make_fetch_response([fr])
        self.mock_llm.return_value = _make_llm_response("Page summary")

        result = await summarize_pages(["https://example.com"])

        self.mock_fetch.assert_awaited_once_with(
            ["https://example.com"], providers=["builtin"], timeout=30.0
        )
        assert result.total_urls == 1
        assert result.total_ok == 1
        assert result.total_failed == 0
        assert result.items[0].summary == "Page summary"
        assert result.items[0].error is None

    async def test_fetch_failure(self):
        from souwen.llm.fetch_summarize import summarize_pages

        fr = _make_fetch_result("https://fail.com", content="", error="Connection timeout")
        self.mock_fetch.return_value = _make_fetch_response([fr])

        result = await summarize_pages(["https://fail.com"])

        assert result.total_ok == 0
        assert result.total_failed == 1
        assert result.items[0].error == "Connection timeout"
        self.mock_llm.assert_not_awaited()

    async def test_llm_failure(self):
        from souwen.llm.fetch_summarize import summarize_pages

        fr = _make_fetch_result(
            "https://example.com", content="Some content with enough words for processing"
        )
        self.mock_fetch.return_value = _make_fetch_response([fr])
        self.mock_llm.side_effect = RuntimeError("LLM timeout")

        result = await summarize_pages(["https://example.com"])

        assert result.total_failed == 1
        assert "LLM error: LLM timeout" == result.items[0].error

    async def test_content_truncation(self):
        from souwen.llm.fetch_summarize import summarize_pages

        long_content = "word " * 10000
        fr = _make_fetch_result("https://example.com", content=long_content)
        self.mock_fetch.return_value = _make_fetch_response([fr])
        self.mock_llm.return_value = _make_llm_response("Truncated summary")

        result = await summarize_pages(["https://example.com"])

        assert result.items[0].content_truncated is True
        assert result.items[0].word_count == 10000
        assert result.items[0].summary == "Truncated summary"

    async def test_multiple_urls_mixed(self):
        from souwen.llm.fetch_summarize import summarize_pages

        results = [
            _make_fetch_result("https://ok.com", content="Good content with enough words"),
            _make_fetch_result("https://fail.com", content="", error="404"),
        ]
        self.mock_fetch.return_value = _make_fetch_response(results)
        self.mock_llm.return_value = _make_llm_response("Summary")

        result = await summarize_pages(["https://ok.com", "https://fail.com"])

        assert result.total_ok == 1
        assert result.total_failed == 1

    async def test_usage_accumulation(self):
        from souwen.llm.fetch_summarize import summarize_pages

        results = [
            _make_fetch_result("https://a.com", content="Content A with enough words"),
            _make_fetch_result("https://b.com", content="Content B with enough words"),
        ]
        self.mock_fetch.return_value = _make_fetch_response(results)
        self.mock_llm.return_value = _make_llm_response("Summary")

        result = await summarize_pages(["https://a.com", "https://b.com"])

        assert result.usage.total_tokens == 60
