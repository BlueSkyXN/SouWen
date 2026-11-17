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
async def test_mcp_streamable_app_reverse_proxy_host_policy(monkeypatch) -> None:
    """反代部署（HF Space 等）下 /mcp 的 Host/Origin 校验必须是精确放行。

    背景：mcp>=1.30 在 FastMCP 默认 host=127.0.0.1 时自动开 DNS-rebinding 防护
    （allowed_hosts 仅 localhost），HF 边缘转发的 Host 是部署域名，线上曾全 421。
    修法不是整体关防护（那会放行任意 Host/Origin），而是合成允许列表：
    loopback + SPACE_HOST（平台注入）或显式配置。

    真实协议链：生产 build_mcp_server 的 streamable app + 真实 initialize 请求，
    断言具体状态码与 serverInfo，不用「不等于 421」当判据。200 响应是 SSE
    长流，用流式请求拿到状态行即关闭，不消费 body（否则测试会等会话超时）。
    """

    import httpx
    from httpx import ASGITransport, AsyncClient

    from souwen.config.models import SouWenConfig
    from souwen.server.mcp_server import build_mcp_server

    config = SouWenConfig(
        mcp_allowed_hosts=["proxy.example.com", "proxy.example.com:*"],
        mcp_allowed_origins=["https://proxy.example.com"],
    )
    app = build_mcp_server(_FakeAgentRuntime(), config).streamable_http_app()
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "proxy-host-probe", "version": "0"},
        },
    }

    async def post(client: AsyncClient, host: str, origin: str | None = None):
        headers = {"Accept": "application/json, text/event-stream", "Host": host}
        if origin:
            headers["Origin"] = origin
        request = client.build_request(
            "POST", "http://testserver/mcp", json=initialize, headers=headers
        )
        response = await client.send(request, stream=True)
        # 200 是 SSE 长流：initialize 响应分多块到达，读前 4KB 足够覆盖
        # serverInfo；拒绝响应（421/403）则读全文。
        body = b""
        try:
            async for chunk in response.aiter_bytes():
                body += chunk
                if response.status_code == 200 and len(body) >= 4096:
                    break
        except httpx.StreamClosed:  # pragma: no cover - defensive
            pass
        await response.aclose()
        return response.status_code, body.decode("utf-8", "replace")

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 允许的 Host → 200 且握手返回 serverInfo
            status, body = await post(client, "proxy.example.com")
            assert status == 200, f"allowed host got {status}"
            assert "serverInfo" in body
            # 通配端口的允许 Host → 200
            status, _ = await post(client, "proxy.example.com:8443")
            assert status == 200
            # 未允许 Host → 421（Host 校验拒绝，先于协议与鉴权）
            status, _ = await post(client, "blueskyxn-souwen.hf.space")
            assert status == 421, f"unlisted host should be rejected with 421, got {status}"
            # 允许 Host + 未允许 Origin → 403（Origin 校验拒绝）
            status, _ = await post(
                client, "proxy.example.com:8443", origin="https://evil.example.com"
            )
            assert status == 403, f"unlisted origin should be rejected with 403, got {status}"
            # 允许 Host + 允许 Origin → 200
            status, _ = await post(
                client, "proxy.example.com:8443", origin="https://proxy.example.com"
            )
            assert status == 200


@pytest.mark.asyncio
async def test_mcp_transport_security_settings_default_and_space_host(monkeypatch) -> None:
    """默认允许表 = loopback 任意端口；HF Spaces 注入 SPACE_HOST 时精确追加该主机。

    SPACE_HOST 是 HF 官方运行时变量（裸主机名，如 ``<space>.hf.space``），值由
    平台控制而非请求头。非法形态（带 scheme/path/通配）必须被忽略，防止把任意
    环境值放大成放行项。
    """

    from souwen.config.models import SouWenConfig
    from souwen.server.mcp_server import _resolve_transport_security

    monkeypatch.delenv("SPACE_HOST", raising=False)
    default = _resolve_transport_security(SouWenConfig())
    assert default.enable_dns_rebinding_protection is True
    assert sorted(default.allowed_hosts) == ["127.0.0.1:*", "[::1]:*", "localhost:*"]
    assert default.allowed_origins == []

    monkeypatch.setenv("SPACE_HOST", "demo-example.hf.space")
    with_space = _resolve_transport_security(SouWenConfig())
    assert "demo-example.hf.space" in with_space.allowed_hosts
    # 通配 HF 域名不行：SPACE_HOST 是具体主机，不是后缀匹配
    assert "other.hf.space" not in with_space.allowed_hosts

    for bad in ("https://evil.example.com/path", "*.hf.space", "no-dot-host", "a b.hf.space"):
        monkeypatch.setenv("SPACE_HOST", bad)
        assert bad not in _resolve_transport_security(SouWenConfig()).allowed_hosts, bad


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


# --- limit 截断经真实共享搜索层到达三个入口（NEXT-SEARCH-LIMIT） ---


class _LimitSearchModule:
    """Stand-in for the search module that runs the real orchestration service."""

    def __init__(self, service) -> None:
        self._service = service

    async def search(self, request, context, execution):
        return await self._service.search(request, context, execution)


def _real_agent_runtime(search_module) -> object:
    """AgentRuntime over a TargetRuntime whose search is the real shared service."""
    from souwen.agent import AgentRuntime
    from souwen.server.v2_runtime import (
        RuntimeMetadata,
        TargetDeliveryServices,
        TargetRuntime,
    )

    services = TargetDeliveryServices(
        search=search_module,
        fetch=None,
        provider_items=(),
        readiness=None,
    )
    runtime = TargetRuntime(
        services=services,
        metadata=RuntimeMetadata(version="test", source_sha=None),
        manager=_NoopManager(),
        browser_client=None,
    )
    return AgentRuntime(runtime, SouWenConfig())


class _NoopManager:
    async def close_all(self) -> None:
        return None


def _limit_service(context, selections, outcomes):
    from souwen.modules.search.api import SearchModuleService

    manager = _LimitManager(outcomes)
    selector = _LimitSelector(selections)
    return SearchModuleService(manager, selector), manager


class _LimitManager:
    def __init__(self, outcomes) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    async def execute(self, adapter_id, request, context, execution):  # noqa: ANN001
        self.calls.append(adapter_id)
        outcome = self.outcomes[adapter_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _LimitSelector:
    def __init__(self, selections) -> None:
        self.selections = selections

    def select_default(self, request):  # noqa: ANN001
        return self.selections

    def select_explicit(self, providers):  # noqa: ANN001
        return self.selections


def _search_fixtures(limit: int):
    """Three providers, three distinct results each; request limit is 3."""
    from souwen.modules.search.application import SearchProviderSelection
    from souwen.platform.provider_spi import (
        PageInfo,
        Provenance,
        ProviderRef,
        RequestContext,
        SearchAttributes,
        SearchItem,
        SearchMeta,
        SearchPage,
    )

    context = RequestContext(request_id="limit-entries")
    selections = tuple(
        SearchProviderSelection(
            provider=ProviderRef(id=f"p{index}", kind="search"),
            adapter_id=f"p{index}-adapter",
            yaml_priority=index,
        )
        for index in range(1, 4)
    )

    def item(provider: str, rank: int) -> SearchItem:
        return SearchItem(
            id=f"{provider}:{rank}",
            title=f"{provider} result {rank}",
            rank=rank,
            url=f"https://example.com/{provider}/{rank}",
            provenance=(Provenance(provider=provider, outcome="success"),),
            attributes=SearchAttributes(),
        )

    outcomes = {
        selection.adapter_id: SearchPage(
            items=tuple(item(selection.provider.id, rank) for rank in (1, 2, 3)),
            page=PageInfo(limit=10),
            meta=SearchMeta(),
            context=context,
        )
        for selection in selections
    }
    return context, selections, outcomes


@pytest.mark.asyncio
async def test_limit_truncation_is_identical_across_http_mcp_and_python() -> None:
    from souwen.server.mcp_server import build_mcp_server

    context, selections, outcomes = _search_fixtures(limit=3)
    service, manager = _limit_service(context, selections, outcomes)
    runtime = _real_agent_runtime(_LimitSearchModule(service))

    python_summary = await runtime.search("query", domain="web", limit=3)
    python_calls = list(manager.calls)
    manager.calls.clear()

    server = build_mcp_server(runtime)
    content_blocks, _structured = await server.call_tool(
        "search", {"query": "query", "domain": "web", "limit": 3}
    )
    mcp_text = content_blocks[0].text
    mcp_calls = list(manager.calls)
    manager.calls.clear()

    http_payload = (
        _app(runtime).post("/search", json={"query": "query", "domain": "web", "limit": 3}).json()
    )
    http_calls = list(manager.calls)

    # 三入口都是真实共享搜索层的同一结果：恰好 3 条，顺序一致。
    assert len(python_summary.results) == 3
    assert [r.url for r in python_summary.results] == [
        "https://example.com/p1/1",
        "https://example.com/p2/1",
        "https://example.com/p3/1",
    ]
    assert len(http_payload["results"]) == 3
    assert [r["url"] for r in http_payload["results"]] == [r.url for r in python_summary.results]
    assert mcp_text == format_search_summary(python_summary)
    assert mcp_text.count("\n") >= 2
    # 每个入口都走真实服务，各自只扇出一次这三个源。
    expected_calls = ["p1-adapter", "p2-adapter", "p3-adapter"]
    assert python_calls == expected_calls
    assert mcp_calls == expected_calls
    assert http_calls == expected_calls


@pytest.mark.asyncio
async def test_limit_truncation_reaches_entries_when_the_first_batch_deduplicates() -> None:
    """第一批去重后不足，后续批次补齐；三入口看到同样的 3 条。"""
    from souwen.server.mcp_server import build_mcp_server
    from souwen.modules.search.application import SearchProviderSelection
    from souwen.platform.provider_spi import (
        PageInfo,
        Provenance,
        ProviderRef,
        RequestContext,
        SearchAttributes,
        SearchItem,
        SearchMeta,
        SearchPage,
    )

    context = RequestContext(request_id="limit-dedup-entries")
    selections = tuple(
        SearchProviderSelection(
            provider=ProviderRef(id=f"p{index}", kind="search"),
            adapter_id=f"p{index}-adapter",
            yaml_priority=index,
        )
        for index in range(1, 5)
    )
    shared = "https://example.com/same"

    def page(*items: SearchItem) -> SearchPage:
        return SearchPage(items=items, page=PageInfo(limit=10), meta=SearchMeta(), context=context)

    def item(item_id: str, provider: str, url: str, rank: int = 1) -> SearchItem:
        return SearchItem(
            id=item_id,
            title=item_id,
            rank=rank,
            url=url,
            provenance=(Provenance(provider=provider, outcome="success"),),
            attributes=SearchAttributes(),
        )

    outcomes = {
        selection.adapter_id: page(
            item(f"{selection.provider.id}:dup", selection.provider.id, shared)
        )
        for selection in selections[:3]
    }
    outcomes[selections[3].adapter_id] = page(
        item("p4:a", "p4", "https://example.com/a"),
        item("p4:b", "p4", "https://example.com/b", rank=2),
    )
    service, manager = _limit_service(context, selections, outcomes)
    runtime = _real_agent_runtime(_LimitSearchModule(service))

    python_summary = await runtime.search("query", domain="web", limit=3)
    python_calls = list(manager.calls)
    manager.calls.clear()

    server = build_mcp_server(runtime)
    content_blocks, _structured = await server.call_tool(
        "search", {"query": "query", "domain": "web", "limit": 3}
    )
    mcp_calls = list(manager.calls)
    manager.calls.clear()

    http_payload = (
        _app(runtime).post("/search", json={"query": "query", "domain": "web", "limit": 3}).json()
    )
    http_calls = list(manager.calls)

    expected_calls = [f"p{index}-adapter" for index in range(1, 5)]
    assert python_calls == expected_calls
    assert mcp_calls == expected_calls
    assert http_calls == expected_calls
    assert len(python_summary.results) == 3
    assert len(http_payload["results"]) == 3
    assert content_blocks[0].text == format_search_summary(python_summary)
    assert [r["url"] for r in http_payload["results"]] == [r.url for r in python_summary.results]
