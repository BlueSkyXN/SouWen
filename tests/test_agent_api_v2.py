"""Agent HTTP/MCP surface, auth, limiter, and runtime composition tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from souwen.config import SouWenConfig
from souwen.modules.fetch.application.reader import FetchPage
from souwen.modules.search.application.projection import (
    CompactSearchItem,
    CompactSearchSummary,
    format_search_summary,
)
from souwen.platform.provider_spi import ProviderError, ProviderErrorCode, SearchRequest
from souwen.server.agent_api import create_agent_api_router
from souwen.server.auth import check_target_user_auth
from souwen.server.limiter import rate_limit_target_data
from souwen.server.v2_runtime import (
    RuntimeMetadata,
    TargetRuntime,
    build_target_runtime,
)


class _FakeAgentRuntime:
    """Deterministic agent runtime double shared by all entry-point tests."""

    def __init__(
        self,
        summary: CompactSearchSummary | None = None,
        page: FetchPage | None = None,
        search_error: ProviderError | None = None,
    ) -> None:
        self.summary = summary or CompactSearchSummary(
            results=(
                CompactSearchItem(
                    title="Attention Is All You Need",
                    url="https://arxiv.org/abs/1706.03762",
                    snippet="We propose the Transformer.",
                    year=2017,
                    authors=("Vaswani", "Shazeer"),
                ),
            ),
            sources=("openalex",),
        )
        self.page = page or FetchPage(
            title="Example",
            url="https://example.com/a",
            content="body",
            total_chars=4,
            start=0,
            next_start=None,
            egress="direct",
            sources=("builtin-fetch",),
        )
        self.search_error = search_error
        self.search_calls: list[dict] = []

    async def search(self, query, *, domain="web", limit=8, providers=None):
        self.search_calls.append({"query": query, "domain": domain, "limit": limit})
        if self.search_error is not None:
            raise self.search_error
        return self.summary

    async def fetch(self, url, *, max_chars=20000, start=0, provider=None):
        return self.page

    def sources(self):
        return (
            _SourceStatus(
                id="openalex",
                kind="search",
                domain="paper",
                availability="available",
                reason="available",
            ),
        )


@dataclass(frozen=True)
class _SourceStatus:
    id: str
    kind: str
    domain: str | None
    availability: str
    reason: str


def _app(
    runtime: _FakeAgentRuntime | None = None,
    *,
    require_user=lambda: None,
    rate_limit=lambda: None,
) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_agent_api_router(
            runtime or _FakeAgentRuntime(),
            require_user=require_user,
            rate_limit=rate_limit,
        )
    )
    return TestClient(app, raise_server_exceptions=False)


def test_search_route_returns_flat_results_and_sources() -> None:
    client = _app()

    response = client.post("/search", json={"query": "transformer", "domain": "paper", "limit": 8})

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == ["openalex"]
    assert payload["partial"] is False
    result = payload["results"][0]
    assert result["title"] == "Attention Is All You Need"
    assert result["url"] == "https://arxiv.org/abs/1706.03762"
    assert result["year"] == 2017
    assert result["authors"] == ["Vaswani", "Shazeer"]
    assert "provenance" not in result
    assert "context" not in payload


def test_fetch_route_returns_pagination_fields() -> None:
    runtime = _FakeAgentRuntime(
        page=FetchPage(
            title="Long page",
            url="https://example.com/long",
            content="0123456789",
            total_chars=100,
            start=10,
            next_start=20,
            egress="direct",
            sources=("builtin-fetch",),
        )
    )
    client = _app(runtime)

    response = client.post(
        "/fetch", json={"url": "https://example.com/long", "max_chars": 10, "start": 10}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Long page"
    assert payload["content"] == "0123456789"
    assert payload["total_chars"] == 100
    assert payload["start"] == 10
    assert payload["next_start"] == 20
    assert payload["egress"] == "direct"


def test_sources_route_lists_domain_and_availability() -> None:
    client = _app()

    response = client.get("/sources")

    assert response.status_code == 200
    entry = response.json()["sources"][0]
    assert entry == {
        "id": "openalex",
        "kind": "search",
        "domain": "paper",
        "availability": "available",
        "reason": "available",
    }


@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    (
        (ProviderErrorCode.INVALID_REQUEST, 400),
        (ProviderErrorCode.RATE_LIMITED, 429),
        (ProviderErrorCode.DEADLINE_EXCEEDED, 504),
        (ProviderErrorCode.POLICY_BLOCKED, 403),
        (ProviderErrorCode.PROVIDER_UNAVAILABLE, 502),
    ),
)
def test_provider_errors_map_to_http_statuses(error_code, expected_status) -> None:
    runtime = _FakeAgentRuntime(search_error=ProviderError(error_code, provider_id="openalex"))
    client = _app(runtime)

    response = client.post("/search", json={"query": "q"})

    assert response.status_code == expected_status
    assert "openalex" in response.json()["detail"]


@pytest.mark.parametrize(
    ("config_password", "headers", "expected"),
    (
        ("user-token", {}, 401),
        ("user-token", {"Authorization": "Bearer wrong"}, 401),
        ("user-token", {"Authorization": "Bearer user-token"}, 200),
        ("user-token", {"X-SouWen-Token": "user-token"}, 200),
        ("user-token", {"Authorization": "Bearer wrong", "X-SouWen-Token": "user-token"}, 200),
        ("", {}, 200),
        ("", {"Authorization": "Bearer anything"}, 401),
    ),
)
def test_agent_auth_is_fail_closed_and_custom_header_is_authoritative(
    monkeypatch, config_password, headers, expected
) -> None:
    from types import SimpleNamespace

    config = SimpleNamespace(
        user_password=config_password,
        effective_user_password=config_password,
    )
    monkeypatch.setattr("souwen.server.auth.get_config", lambda: config)
    client = _app(require_user=check_target_user_auth)

    response = client.get("/sources", headers=headers)

    assert response.status_code == expected


def test_rate_limit_uses_credential_digest_and_custom_header_precedence(monkeypatch) -> None:
    identities: list[str] = []
    monkeypatch.setattr("souwen.server.limiter._target_data_limiter.check", identities.append)
    client = _app(rate_limit=rate_limit_target_data)

    client.get("/sources", headers={"Authorization": "Bearer user-token"})
    client.get(
        "/sources",
        headers={"Authorization": "Bearer ignored", "X-SouWen-Token": "user-token"},
    )

    assert identities[0] == identities[1]
    assert identities[0].startswith("credential:")
    assert "user-token" not in identities[0]


def test_limiter_error_keeps_headers() -> None:
    def limited() -> None:
        raise HTTPException(
            status_code=429,
            headers={
                "Retry-After": "5",
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "123456",
            },
        )

    response = _app(rate_limit=limited).get("/sources")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "5"
    assert response.headers["x-ratelimit-limit"] == "60"
    assert response.headers["x-ratelimit-remaining"] == "0"
    assert response.headers["x-ratelimit-reset"] == "123456"


def test_search_validation_rejects_unknown_domain_and_bad_limit() -> None:
    client = _app()

    assert client.post("/search", json={"query": "q", "domain": "nope"}).status_code == 422
    assert client.post("/search", json={"query": "q", "limit": 0}).status_code == 422
    assert client.post("/search", json={"query": ""}).status_code == 422


# --- 三入口一致性（SPEC 2.5）：同一假 runtime，MCP、HTTP、Python 内容一致 ---


@pytest.mark.asyncio
async def test_mcp_exposes_exactly_search_and_fetch(monkeypatch) -> None:
    from souwen.server.mcp_server import build_mcp_server

    server = build_mcp_server(_FakeAgentRuntime())

    tools = await server.list_tools()

    assert [tool.name for tool in tools] == ["search", "fetch"]


@pytest.mark.asyncio
async def test_three_entries_agree_on_the_same_underlying_result(monkeypatch) -> None:
    import souwen.agent as agent_module
    from souwen.server.mcp_server import build_mcp_server

    fake = _FakeAgentRuntime()
    monkeypatch.setattr(agent_module, "get_agent_runtime", lambda: fake)

    python_text = await agent_module.search("transformer", domain="paper", limit=8)

    server = build_mcp_server(fake)
    content_blocks, _structured = await server.call_tool(
        "search", {"query": "transformer", "domain": "paper"}
    )
    mcp_text = content_blocks[0].text

    http_payload = (
        _app(fake)
        .post("/search", json={"query": "transformer", "domain": "paper", "limit": 8})
        .json()
    )

    expected = format_search_summary(fake.summary)
    assert python_text == expected
    assert mcp_text == expected
    assert http_payload["results"][0]["title"] == fake.summary.results[0].title
    assert http_payload["sources"] == list(fake.summary.sources)


# --- 保留的 runtime 组合测试（原 delivery 合同测试中仍有效的部分） ---


def test_target_runtime_has_one_default_provider_for_every_public_search_domain(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = build_target_runtime(SouWenConfig())
    selector = runtime.services.search._selector

    expected = {
        "paper": "huggingface",
        "book": "library_of_congress",
        "web": "yahoo",
        "news": "duckduckgo_news",
        "code": "stackoverflow",
        "community": "juejin",
        "wiki": "wikipedia",
    }

    selected = {
        domain: selector.select_default(SearchRequest(query="default", domains=(domain,)))[
            0
        ].provider.id
        for domain in expected
    }

    assert selected == expected
    for domain in ("patent", "videos"):
        with pytest.raises(ProviderError) as empty_domain:
            selector.select_default(SearchRequest(query="default", domains=(domain,)))
        assert empty_domain.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE


@pytest.mark.asyncio
async def test_runtime_close_attempts_browser_after_provider_close_failure() -> None:
    class _Manager:
        async def close_all(self) -> None:
            raise RuntimeError("provider close failed")

    class _Worker:
        closed = False

        async def close(self) -> None:
            self.closed = True

    class _Services:
        pass

    worker = _Worker()
    runtime = TargetRuntime(
        services=_Services(),
        metadata=RuntimeMetadata(version="2.0.0rc6", source_sha="a" * 40),
        manager=_Manager(),
        browser_client=worker,
    )

    with pytest.raises(RuntimeError, match="provider close failed"):
        await runtime.close()

    assert worker.closed is True
