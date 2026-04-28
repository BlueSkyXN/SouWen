"""Tests for souwen.llm.fetch_summarize and souwen.llm.deep_search modules."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from souwen.llm.deep_search import _extract_urls_round_robin
from souwen.llm.models import LLMResponse, LLMUsage
from souwen.models import FetchResponse, FetchResult, SearchResponse, SourceType, WebSearchResult


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


# ── deep_search tests ────────────────────────────────────


class TestExtractUrlsRoundRobin:
    def _make_response(
        self,
        source: SourceType,
        urls: list[tuple[str, str]],
    ) -> SearchResponse:
        """Create a SearchResponse with web results."""
        return SearchResponse(
            query="test",
            source=source,
            results=[
                WebSearchResult(source=source, title=title, url=url, engine="test")
                for url, title in urls
            ],
        )

    def test_basic_round_robin(self):
        r1 = self._make_response(
            SourceType.WEB_DUCKDUCKGO,
            [("https://a.com", "A"), ("https://b.com", "B")],
        )
        r2 = self._make_response(
            SourceType.WEB_BRAVE,
            [("https://c.com", "C"), ("https://d.com", "D")],
        )

        result = _extract_urls_round_robin([r1, r2], max_urls=4)

        urls = [u for u, _, _ in result]
        assert urls == ["https://a.com", "https://c.com", "https://b.com", "https://d.com"]

    def test_dedup_by_normalized_url(self):
        r1 = self._make_response(SourceType.WEB_DUCKDUCKGO, [("https://example.com/page", "A")])
        r2 = self._make_response(SourceType.WEB_BRAVE, [("https://Example.com/Page", "B")])

        result = _extract_urls_round_robin([r1, r2], max_urls=5)

        assert len(result) == 1

    def test_max_urls_limit(self):
        r1 = self._make_response(
            SourceType.WEB_DUCKDUCKGO,
            [("https://a.com", "A"), ("https://b.com", "B"), ("https://c.com", "C")],
        )

        result = _extract_urls_round_robin([r1], max_urls=2)

        assert len(result) == 2

    def test_empty_responses(self):
        result = _extract_urls_round_robin([], max_urls=5)

        assert result == []


class TestDeepSummarize:
    @pytest.fixture(autouse=True)
    def _mock_deps(self):
        with (
            patch("souwen.facade.search.search", new_callable=AsyncMock) as self.mock_search,
            patch("souwen.web.fetch.fetch_content", new_callable=AsyncMock) as self.mock_fetch,
            patch("souwen.llm.deep_search.llm_complete", new_callable=AsyncMock) as self.mock_llm,
            patch("souwen.llm.deep_search.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = _mock_config()
            yield

    def _make_search_response(self) -> list[SearchResponse]:
        return [
            SearchResponse(
                query="test query",
                source=SourceType.WEB_DUCKDUCKGO,
                results=[
                    WebSearchResult(
                        source=SourceType.WEB_DUCKDUCKGO,
                        title="Result 1",
                        url="https://example.com/1",
                        engine="duckduckgo",
                    ),
                    WebSearchResult(
                        source=SourceType.WEB_DUCKDUCKGO,
                        title="Result 2",
                        url="https://example.com/2",
                        engine="duckduckgo",
                    ),
                ],
            )
        ]

    async def test_success(self):
        from souwen.llm.deep_search import deep_summarize

        self.mock_search.return_value = self._make_search_response()
        self.mock_fetch.return_value = _make_fetch_response(
            [_make_fetch_result("https://example.com/1", content="Long content " * 30)]
        )
        self.mock_llm.side_effect = [
            _make_llm_response("Extraction from page 1"),
            _make_llm_response("Final synthesis"),
        ]

        result = await deep_summarize("test query", domain="web", max_fetch=2)

        self.mock_search.assert_awaited_once_with(
            "test query", domain="web", sources=None, limit=10
        )
        self.mock_fetch.assert_awaited_once_with(
            ["https://example.com/1", "https://example.com/2"],
            providers=["builtin"],
            timeout=30.0,
        )
        assert result.summary == "Final synthesis"
        assert result.pages_synthesized == 1
        assert len(result.citations) == 1
        assert self.mock_llm.call_count == 2

    async def test_no_search_results(self):
        from souwen.llm.deep_search import deep_summarize

        self.mock_search.return_value = []

        with pytest.raises(ValueError, match="No search results"):
            await deep_summarize("test query")

    async def test_no_urls(self):
        from souwen.llm.deep_search import deep_summarize

        self.mock_search.return_value = [
            SearchResponse(query="test query", source=SourceType.WEB_DUCKDUCKGO, results=[])
        ]

        with pytest.raises(ValueError, match="No search results"):
            await deep_summarize("test query")

    async def test_no_usable_content(self):
        from souwen.llm.deep_search import deep_summarize

        self.mock_search.return_value = self._make_search_response()
        self.mock_fetch.return_value = _make_fetch_response(
            [_make_fetch_result("https://example.com/1", content="", error="timeout")]
        )

        with pytest.raises(ValueError, match="No pages with usable content"):
            await deep_summarize("test query", domain="web", max_fetch=1)

    async def test_all_extractions_fail(self):
        from souwen.llm.deep_search import deep_summarize

        self.mock_search.return_value = self._make_search_response()
        self.mock_fetch.return_value = _make_fetch_response(
            [_make_fetch_result("https://example.com/1", content="Content " * 30)]
        )
        self.mock_llm.side_effect = RuntimeError("extract failed")

        with pytest.raises(ValueError, match="All page extractions failed"):
            await deep_summarize("test query", domain="web", max_fetch=1)

    async def test_usage_accumulation(self):
        from souwen.llm.deep_search import deep_summarize

        self.mock_search.return_value = self._make_search_response()
        self.mock_fetch.return_value = _make_fetch_response(
            [
                _make_fetch_result("https://example.com/1", content="Content " * 30),
                _make_fetch_result("https://example.com/2", content="Content " * 30),
            ]
        )
        self.mock_llm.side_effect = [
            _make_llm_response("Extract 1"),
            _make_llm_response("Extract 2"),
            _make_llm_response("Synthesis"),
        ]

        result = await deep_summarize("test", domain="web", max_fetch=2)

        assert result.usage.total_tokens == 90
