"""Google Patents scraper fallback tests."""

from __future__ import annotations

from typing import Any

import pytest

from souwen.core.exceptions import ConfigError, SourceUnavailableError
from souwen.patent.google_patents_scraper import GooglePatentsScraper


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        json_data: Any | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._json_data = json_data if json_data is not None else {}

    def json(self) -> Any:
        return self._json_data


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeBrowserResponse:
    def __init__(self, status: int) -> None:
        self.status = status


class _FakeRoute:
    def __init__(self, url: str, *, has_fallback: bool = True) -> None:
        self.request = _FakeRequest(url)
        self.actions: list[str] = []
        if not has_fallback:
            self.fallback = None

    async def fallback(self) -> None:
        self.actions.append("fallback")

    async def continue_(self) -> None:
        self.actions.append("continue")

    async def abort(self) -> None:
        self.actions.append("abort")


class _FakePage:
    def __init__(self, html: str, *, goto_status: int = 200) -> None:
        self.html = html
        self.goto_status = goto_status
        self.routes: list[tuple[str, Any]] = []
        self.gotos: list[dict[str, Any]] = []
        self.waits: list[dict[str, Any]] = []

    async def route(self, pattern: str, handler: Any) -> None:
        self.routes.append((pattern, handler))

    async def goto(self, url: str, **kwargs: Any) -> None:
        self.gotos.append({"url": url, **kwargs})
        return _FakeBrowserResponse(self.goto_status)

    async def wait_for_selector(self, selector: str, **kwargs: Any) -> None:
        self.waits.append({"selector": selector, **kwargs})

    async def content(self) -> str:
        return self.html


class _FakePageContext:
    def __init__(self, page: _FakePage) -> None:
        self.page = page

    async def __aenter__(self) -> _FakePage:
        return self.page

    async def __aexit__(self, *args: Any) -> None:
        return None


class _FakePool:
    def __init__(self, page: _FakePage) -> None:
        self.fake_page = page
        self.page_calls: list[dict[str, Any]] = []

    def page(self, **kwargs: Any) -> _FakePageContext:
        self.page_calls.append(kwargs)
        return _FakePageContext(self.fake_page)


@pytest.mark.asyncio
async def test_parse_xhr_maps_live_scalar_fields():
    scraper = GooglePatentsScraper(min_delay=0, max_delay=0)
    try:
        response = scraper._parse_search_response(
            {
                "results": {
                    "cluster": [
                        {
                            "result": [
                                {
                                    "patent": {
                                        "title": "Anomaly detection with <b>machine learning</b>",
                                        "snippet": "Processing scores using <b>machine-learning</b> models.",
                                        "publication_date": "2025-10-07",
                                        "filing_date": "20220218",
                                        "inventor": "Sudhakar Muddu",
                                        "assignee": "Splunk Inc.",
                                        "publication_number": "US12438891B1",
                                        "cpc": "G06N20/00",
                                    }
                                }
                            ]
                        }
                    ]
                }
            },
            "machine learning",
        )
    finally:
        await scraper.close()

    assert response.total_results == 1
    result = response.results[0]
    assert result.patent_id == "US12438891B1"
    assert result.title == "Anomaly detection with machine learning"
    assert result.abstract == "Processing scores using machine-learning models."
    assert result.publication_date and result.publication_date.isoformat() == "2025-10-07"
    assert result.filing_date and result.filing_date.isoformat() == "2022-02-18"
    assert result.inventors == ["Sudhakar Muddu"]
    assert [applicant.name for applicant in result.applicants] == ["Splunk Inc."]
    assert result.cpc_codes == ["G06N20/00"]


@pytest.mark.asyncio
async def test_search_uses_playwright_fallback_when_static_paths_are_empty(monkeypatch):
    rendered_html = """
    <html><body>
      <search-result-item>
        <a href="/patent/US1234567A/en"><h3>Rendered patent result</h3></a>
        <p class="abstract">Rendered abstract text.</p>
      </search-result-item>
    </body></html>
    """
    fake_page = _FakePage(rendered_html)
    fake_pool = _FakePool(fake_page)

    async def fake_fetch(self: GooglePatentsScraper, url: str, **kwargs: Any) -> _FakeResponse:
        del self, kwargs
        if url.endswith("/xhr/query"):
            return _FakeResponse(json_data={"results": {"cluster": []}})
        return _FakeResponse(text="<html><body></body></html>")

    monkeypatch.setattr(GooglePatentsScraper, "_fetch", fake_fetch)
    monkeypatch.setattr(
        "souwen.patent.google_patents_scraper.get_browser_pool",
        lambda **kwargs: fake_pool,
    )

    scraper = GooglePatentsScraper(min_delay=0, max_delay=0)
    try:
        response = await scraper.search("rendered patent", num_results=3)
    finally:
        await scraper.close()

    assert response.source == "google_patents"
    assert response.total_results == 1
    assert response.results[0].patent_id == "US1234567A"
    assert response.results[0].title == "Rendered patent result"
    assert response.results[0].abstract == "Rendered abstract text."
    assert fake_page.gotos[0]["url"].startswith("https://patents.google.com/?")
    assert fake_page.gotos[0]["wait_until"] == "domcontentloaded"
    assert fake_page.routes[0][0] == "**/*"
    assert fake_pool.page_calls[0]["user_agent"]


@pytest.mark.asyncio
async def test_playwright_fallback_missing_runtime_returns_static_empty(monkeypatch):
    async def fake_fetch(self: GooglePatentsScraper, url: str, **kwargs: Any) -> _FakeResponse:
        del self, url, kwargs
        return _FakeResponse(text="<html><body></body></html>")

    def missing_pool(**kwargs: Any) -> Any:
        del kwargs
        raise ConfigError("playwright", "Playwright")

    monkeypatch.setattr(GooglePatentsScraper, "_fetch", fake_fetch)
    monkeypatch.setattr("souwen.patent.google_patents_scraper.get_browser_pool", missing_pool)

    scraper = GooglePatentsScraper(min_delay=0, max_delay=0)
    try:
        response = await scraper._search_html("no hits", num_results=2)
    finally:
        await scraper.close()

    assert response.source == "google_patents"
    assert response.total_results == 0
    assert response.results == []


@pytest.mark.asyncio
async def test_search_raises_when_google_blocks_browser_fallback(monkeypatch):
    blocked_html = """
    <html><head><title>Sorry...</title></head><body>
      We're sorry... but your computer or network may be sending automated queries.
      To protect our users, we can't process your request right now.
    </body></html>
    """
    fake_page = _FakePage(blocked_html, goto_status=503)
    fake_pool = _FakePool(fake_page)

    async def fake_fetch(self: GooglePatentsScraper, url: str, **kwargs: Any) -> _FakeResponse:
        del self, kwargs
        if url.endswith("/xhr/query"):
            return _FakeResponse(json_data={"results": {"cluster": []}})
        return _FakeResponse(text="<html><body></body></html>")

    monkeypatch.setattr(GooglePatentsScraper, "_fetch", fake_fetch)
    monkeypatch.setattr(
        "souwen.patent.google_patents_scraper.get_browser_pool",
        lambda **kwargs: fake_pool,
    )

    scraper = GooglePatentsScraper(min_delay=0, max_delay=0)
    try:
        with pytest.raises(SourceUnavailableError, match="blocked automated search"):
            await scraper.search("machine learning", num_results=3)
    finally:
        await scraper.close()


@pytest.mark.asyncio
async def test_google_patents_browser_guard_blocks_private_requests():
    scraper = GooglePatentsScraper(min_delay=0, max_delay=0)
    page = _FakePage("<html></html>")
    try:
        await scraper._install_page_ssrf_guard(page)
        _, handler = page.routes[0]

        blocked = _FakeRoute("http://127.0.0.1/internal")
        await handler(blocked)
        assert blocked.actions == ["abort"]

        allowed = _FakeRoute("https://93.184.216.34/static.js")
        await handler(allowed)
        assert allowed.actions == ["fallback"]
    finally:
        await scraper.close()
