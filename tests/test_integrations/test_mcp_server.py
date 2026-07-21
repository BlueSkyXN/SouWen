from __future__ import annotations

import importlib
import json

import pytest

from souwen.integrations.mcp import server as mcp_server


@pytest.fixture(autouse=True)
def _isolate_mcp_plugin_state(monkeypatch, clean_registry, clean_fetch_handlers):
    """MCP tests must not autoload real entry point plugins from the developer env."""

    from souwen.plugin import _PLUGINS

    saved_plugins = dict(_PLUGINS)
    monkeypatch.setenv("SOUWEN_PLUGIN_AUTOLOAD", "0")
    mcp_server._MCP_PLUGINS_BOOTSTRAPPED = False
    try:
        yield
    finally:
        _PLUGINS.clear()
        _PLUGINS.update(saved_plugins)
        mcp_server._MCP_PLUGINS_BOOTSTRAPPED = False


class _FakeTool:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeTextContent:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeServer:
    def __init__(self, name: str):
        self.name = name
        self._list_tools = None
        self._call_tool = None

    def list_tools(self):
        def decorator(fn):
            self._list_tools = fn
            return fn

        return decorator

    def call_tool(self):
        def decorator(fn):
            self._call_tool = fn
            return fn

        return decorator


def _assert_string_or_array_schema(schema: dict) -> None:
    assert schema["oneOf"] == [
        {"type": "string"},
        {"type": "array", "items": {"type": "string"}},
    ]


@pytest.mark.asyncio
async def test_citation_tools_are_registered_and_dispatch_public_facades(monkeypatch):
    from souwen.models import CitationCountResponse, CitationGraphResponse

    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    async def count(identifier: str):
        assert identifier == "doi:10.1/x"
        return CitationCountResponse(
            identifier={"scheme": "doi", "value": "10.1/x"},
            count=4,
            source_url="https://example.test/count",
        )

    async def incoming(identifier: str, *, max_edges: int):
        assert (identifier, max_edges) == ("doi:10.1/x", 2)
        return CitationGraphResponse(
            identifier={"scheme": "doi", "value": "10.1/x"},
            relation="citations",
            total_edges=0,
            returned_edges=0,
            source_url="https://example.test/incoming",
        )

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda _name: False)
    monkeypatch.setattr("souwen.citations.get_citation_count", count)
    monkeypatch.setattr("souwen.citations.get_incoming_citations", incoming)

    mcp_server.create_server()
    tools = await created["server"]._list_tools()
    names = {tool.name for tool in tools}
    assert {"citation_count", "citation_incoming", "citation_references"} <= names
    count_result = await created["server"]._call_tool(
        "citation_count", {"identifier": "doi:10.1/x"}
    )
    incoming_result = await created["server"]._call_tool(
        "citation_incoming", {"identifier": "doi:10.1/x", "max_edges": 2}
    )
    assert json.loads(count_result[0].text)["count"] == 4
    assert json.loads(incoming_result[0].text)["relation"] == "citations"


@pytest.mark.asyncio
async def test_create_server_bootstraps_plugins_before_fetch_tool(
    monkeypatch, clean_registry, clean_fetch_handlers
):
    """Standalone MCP stdio must load runtime plugins before tools dispatch."""

    from souwen.models import FetchResponse, FetchResult
    from souwen.plugin import PluginLoadResult
    from souwen.registry.adapter import MethodSpec, SourceAdapter
    from souwen.registry.loader import lazy
    from souwen.registry.views import _reg_external
    from souwen.web.fetch import register_fetch_handler

    created: dict[str, _FakeServer] = {}
    cfg = object()
    calls = []
    provider = "mcp_runtime_fetch_probe"

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    async def fake_handler(urls, timeout, **_kwargs):
        return FetchResponse(
            urls=urls,
            results=[
                FetchResult(
                    url=url,
                    final_url=url,
                    source=provider,
                    content="plugin ok",
                )
                for url in urls
            ],
            total=len(urls),
            total_ok=len(urls),
            total_failed=0,
            provider=provider,
            providers=[provider],
        )

    def fake_ensure_plugins_loaded(config):
        calls.append(config)
        assert _reg_external(
            SourceAdapter(
                name=provider,
                domain="fetch",
                integration="scraper",
                description="MCP runtime fetch provider probe",
                config_field=None,
                client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
                methods={"fetch": MethodSpec("fetch")},
                category="fetch",
            )
        )
        register_fetch_handler(provider, fake_handler, owner=provider)
        return PluginLoadResult(
            loaded_plugins=(provider,),
            loaded_adapters=(provider,),
            skipped=(),
            errors=(),
        )

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)
    monkeypatch.setenv("SOUWEN_EDITION", "full")
    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)
    monkeypatch.setattr("souwen.plugin.ensure_plugins_loaded", fake_ensure_plugins_loaded)

    try:
        mcp_server._MCP_PLUGINS_BOOTSTRAPPED = False
        mcp_server.create_server()
        result = await created["server"]._call_tool(
            "fetch_content",
            {"urls": ["https://1.1.1.1"], "provider": provider},
        )

        payload = json.loads(result[0].text)
        assert calls == [cfg]
        assert payload["total_ok"] == 1
        assert payload["results"][0]["source"] == provider
        assert payload["results"][0]["content"] == "plugin ok"
    finally:
        mcp_server._MCP_PLUGINS_BOOTSTRAPPED = False


@pytest.mark.asyncio
async def test_search_papers_tool_uses_registry_defaults(monkeypatch):
    """MCP 省略 ``sources`` 时，应透传 ``None`` 并暴露最新默认源说明。"""
    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)

    async def fake_dispatch(*args, **kwargs):
        raise AssertionError("unexpected bilibili dispatch")

    monkeypatch.setattr(mcp_server, "dispatch_bilibili_tool", fake_dispatch)

    search_mod = importlib.import_module("souwen.search")
    captured: dict = {}

    async def fake_search_papers(query, sources=None, per_page=10, **kwargs):
        captured["query"] = query
        captured["sources"] = sources
        captured["per_page"] = per_page
        return []

    monkeypatch.setattr(search_mod, "search_papers", fake_search_papers)

    mcp_server.create_server()
    server = created["server"]

    tools = await server._list_tools()
    paper_tool = next(tool for tool in tools if tool.name == "search_papers")
    _assert_string_or_array_schema(paper_tool.inputSchema["properties"]["sources"])
    assert paper_tool.inputSchema["properties"]["sources"]["description"].endswith(
        mcp_server._default_paper_sources_label()
    )

    result = await server._call_tool("search_papers", {"query": "foo"})
    assert captured == {"query": "foo", "sources": None, "per_page": 5}
    assert len(result) == 1
    assert result[0].text == "[]"


@pytest.mark.asyncio
async def test_search_books_tool_uses_registry_defaults(monkeypatch):
    """MCP 图书搜索应公开 book default，并在省略 sources 时透传 ``None``。"""
    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)

    async def fake_dispatch(*args, **kwargs):
        raise AssertionError("unexpected bilibili dispatch")

    monkeypatch.setattr(mcp_server, "dispatch_bilibili_tool", fake_dispatch)

    search_mod = importlib.import_module("souwen.search")
    captured: dict = {}

    async def fake_search_books(query, sources=None, per_page=10, **kwargs):
        captured["query"] = query
        captured["sources"] = sources
        captured["per_page"] = per_page
        return []

    monkeypatch.setattr(search_mod, "search_books", fake_search_books)

    mcp_server.create_server()
    server = created["server"]

    tools = await server._list_tools()
    book_tool = next(tool for tool in tools if tool.name == "search_books")
    _assert_string_or_array_schema(book_tool.inputSchema["properties"]["sources"])
    assert book_tool.inputSchema["properties"]["sources"]["description"].endswith(
        mcp_server._default_book_sources_label()
    )

    result = await server._call_tool("search_books", {"query": "foo"})
    assert captured == {"query": "foo", "sources": None, "per_page": 5}
    assert len(result) == 1
    assert result[0].text == "[]"


@pytest.mark.asyncio
async def test_search_research_outputs_tool_uses_registry_defaults(monkeypatch):
    """MCP research-output tool should expose and dispatch the registry default."""
    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)

    async def fake_dispatch(*args, **kwargs):
        raise AssertionError("unexpected bilibili dispatch")

    monkeypatch.setattr(mcp_server, "dispatch_bilibili_tool", fake_dispatch)
    search_mod = importlib.import_module("souwen.search")
    captured: dict = {}

    async def fake_search(query, sources=None, per_page=10, **kwargs):
        captured.update(query=query, sources=sources, per_page=per_page)
        return []

    monkeypatch.setattr(search_mod, "search_research_outputs", fake_search)
    mcp_server.create_server()
    server = created["server"]

    tools = await server._list_tools()
    tool = next(item for item in tools if item.name == "search_research_outputs")
    _assert_string_or_array_schema(tool.inputSchema["properties"]["sources"])
    assert tool.inputSchema["properties"]["sources"]["description"].endswith(
        mcp_server._default_research_output_sources_label()
    )

    result = await server._call_tool("search_research_outputs", {"query": "climate"})
    assert captured == {"query": "climate", "sources": None, "per_page": 5}
    assert len(result) == 1
    assert result[0].text == "[]"


@pytest.mark.asyncio
async def test_search_patents_tool_uses_registry_defaults(monkeypatch):
    """MCP 专利搜索省略 ``sources`` 时，也应透传 ``None`` 给 registry 默认源。"""
    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)

    async def fake_dispatch(*args, **kwargs):
        raise AssertionError("unexpected bilibili dispatch")

    monkeypatch.setattr(mcp_server, "dispatch_bilibili_tool", fake_dispatch)

    search_mod = importlib.import_module("souwen.search")
    captured: dict = {}

    async def fake_search_patents(query, sources=None, per_page=10, **kwargs):
        captured["query"] = query
        captured["sources"] = sources
        captured["per_page"] = per_page
        return []

    monkeypatch.setattr(search_mod, "search_patents", fake_search_patents)

    mcp_server.create_server()
    server = created["server"]

    tools = await server._list_tools()
    patent_tool = next(tool for tool in tools if tool.name == "search_patents")
    _assert_string_or_array_schema(patent_tool.inputSchema["properties"]["sources"])
    assert patent_tool.inputSchema["properties"]["sources"]["description"].endswith(
        mcp_server._default_patent_sources_label()
    )

    result = await server._call_tool("search_patents", {"query": "foo"})
    assert captured == {"query": "foo", "sources": None, "per_page": 5}
    assert len(result) == 1
    assert result[0].text == "[]"


@pytest.mark.asyncio
async def test_web_search_tool_mentions_registry_defaults(monkeypatch):
    """MCP web_search 工具说明应同步 registry 的 web 默认源。"""
    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])

    mcp_server.create_server()
    tools = await created["server"]._list_tools()
    web_tool = next(tool for tool in tools if tool.name == "web_search")

    expected_label = mcp_server._default_web_engines_label()
    assert expected_label in web_tool.description
    _assert_string_or_array_schema(web_tool.inputSchema["properties"]["engines"])
    assert web_tool.inputSchema["properties"]["engines"]["description"].endswith(expected_label)


@pytest.mark.asyncio
async def test_search_tools_normalize_string_source_arguments(monkeypatch):
    """MCP 搜索工具误传字符串 sources/engines 时应归一化为单元素列表。"""
    from souwen.models import WebSearchResponse

    created: dict[str, _FakeServer] = {}
    captured: dict[str, list[str] | None] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    async def fake_search_papers(query, sources=None, per_page=10, **_kwargs):
        captured["paper_sources"] = sources
        return []

    async def fake_search_patents(query, sources=None, per_page=10, **_kwargs):
        captured["patent_sources"] = sources
        return []

    async def fake_web_search(query, engines=None, max_results_per_engine=10, **_kwargs):
        captured["web_engines"] = engines
        return WebSearchResponse(query=query, source="duckduckgo", results=[], total_results=0)

    search_mod = importlib.import_module("souwen.search")
    web_search_mod = importlib.import_module("souwen.web.search")

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)
    monkeypatch.setattr(search_mod, "search_papers", fake_search_papers)
    monkeypatch.setattr(search_mod, "search_patents", fake_search_patents)
    monkeypatch.setattr(web_search_mod, "web_search", fake_web_search)

    mcp_server.create_server()
    server = created["server"]

    await server._call_tool("search_papers", {"query": "llm", "sources": "openalex"})
    await server._call_tool("search_patents", {"query": "battery", "sources": "google_patents"})
    await server._call_tool("web_search", {"query": "sou", "engines": "duckduckgo"})

    assert captured == {
        "paper_sources": ["openalex"],
        "patent_sources": ["google_patents"],
        "web_engines": ["duckduckgo"],
    }


@pytest.mark.asyncio
async def test_search_tools_reject_invalid_sources_argument(monkeypatch):
    """MCP 搜索工具对非法 sources 类型返回清晰错误。"""
    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)

    mcp_server.create_server()
    result = await created["server"]._call_tool(
        "search_papers",
        {
            "query": "llm",
            "sources": {"name": "openalex"},
        },
    )

    assert result[0].text.startswith("Error: ValueError:")
    assert "sources 必须是字符串或字符串列表" in result[0].text


@pytest.mark.asyncio
async def test_tool_errors_redact_secret_detail(monkeypatch):
    """MCP 工具异常文本不应泄漏 token、Cookie 或 URL query secret。"""
    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    async def fake_search_papers(*args, **kwargs):
        raise RuntimeError(
            "upstream failed token=mcp-secret Cookie: sid=session-secret "
            "callback https://mcp.example/cb?apiKey=url-secret&safe=1"
        )

    search_mod = importlib.import_module("souwen.search")

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)
    monkeypatch.setattr(search_mod, "search_papers", fake_search_papers)

    mcp_server.create_server()
    result = await created["server"]._call_tool("search_papers", {"query": "llm"})

    text = result[0].text
    assert text.startswith("Error: RuntimeError:")
    assert "mcp-secret" not in text
    assert "session-secret" not in text
    assert "url-secret" not in text
    assert "token:***" in text
    assert "Cookie:***" in text
    assert "apiKey=***" in text
    assert "safe=1" in text


@pytest.mark.asyncio
async def test_fetch_content_tool_schema_uses_registry_fetch_providers(monkeypatch):
    """MCP fetch_content 工具说明应同步 fetch provider 能力。"""
    from souwen.config import get_config
    from souwen.feature_matrix import declared_fetch_provider_names

    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])

    mcp_server.create_server()
    tools = await created["server"]._list_tools()
    fetch_tool = next(tool for tool in tools if tool.name == "fetch_content")

    props = fetch_tool.inputSchema["properties"]
    expected_names = mcp_server._fetch_provider_names()
    expected_label = " / ".join(expected_names)
    cfg = get_config()
    expected_declared_names = set(declared_fetch_provider_names(cfg.edition))
    projection = props["provider"]["x-souwen-provider-projection"]

    assert expected_names[0] == "builtin"
    assert set(expected_names) == expected_declared_names
    assert "metaso" in expected_names
    assert "arxiv_fulltext" not in expected_names
    assert expected_label in fetch_tool.description
    assert expected_label in props["provider"]["description"]
    assert expected_label in props["providers"]["description"]
    assert projection is props["providers"]["x-souwen-provider-projection"]
    assert set(projection) == {
        "declared",
        "available",
        "unavailable",
        "upgrade_required",
        "providers",
    }
    assert set(projection["declared"]) == expected_declared_names
    assert all(
        {
            "name",
            "min_edition",
            "edition_available",
            "edition_reason",
            "runtime_available",
            "runtime_reason",
            "available",
        }
        == set(item)
        for item in projection["providers"]
    )
    assert "当前 edition 声明" in fetch_tool.description
    assert "当前 runtime 可导入" in fetch_tool.description
    assert "当前可选" not in fetch_tool.description
    _assert_string_or_array_schema(props["urls"])
    _assert_string_or_array_schema(props["providers"])
    assert props["strategy"]["enum"] == ["fallback", "fanout"]
    assert props["strategy"]["default"] == "fallback"
    assert "builtin / scrapling" in props["selector"]["description"]
    assert (
        props["respect_robots_txt"]["description"] == "是否遵守 robots.txt（provider 支持时生效）"
    )


@pytest.mark.parametrize("edition", ["basic", "pro", "full"])
def test_fetch_provider_names_follow_feature_matrix(monkeypatch, edition):
    """MCP provider schema source should be feature_matrix, with builtin ordered first."""
    from souwen.config import get_config
    from souwen.feature_matrix import declared_fetch_provider_names

    monkeypatch.setenv("SOUWEN_EDITION", edition)
    get_config.cache_clear()

    names = mcp_server._fetch_provider_names()
    expected = list(declared_fetch_provider_names(edition))
    if "builtin" in expected:
        expected = ["builtin", *(name for name in expected if name != "builtin")]

    assert names == expected


@pytest.mark.asyncio
async def test_fetch_content_tool_schema_filters_fetch_providers_by_basic_edition(monkeypatch):
    """MCP 工具完整保留，并明确把 basic edition 声明与 runtime 分开。"""
    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])

    mcp_server.create_server()
    tools = await created["server"]._list_tools()
    fetch_tool = next(tool for tool in tools if tool.name == "fetch_content")
    props = fetch_tool.inputSchema["properties"]

    assert mcp_server._fetch_provider_names() == ["builtin", "mcp", "site_crawler"]
    assert "builtin / mcp / site_crawler" in fetch_tool.description
    assert "builtin / mcp / site_crawler" in props["provider"]["description"]
    projection = props["provider"]["x-souwen-provider-projection"]
    assert projection["declared"] == ["builtin", "mcp", "site_crawler"]
    assert any(item["name"] == "jina_reader" for item in projection["upgrade_required"])
    assert "jina_reader" not in fetch_tool.description
    assert "crawl4ai" not in fetch_tool.description


@pytest.mark.asyncio
async def test_fetch_content_tool_schema_reports_missing_runtime_without_hiding_provider_id(
    monkeypatch,
):
    """A declared provider with a missing SDK remains addressable but is not called available."""
    from souwen.feature_matrix import FetchProviderRuntimeStatus

    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    statuses = (
        FetchProviderRuntimeStatus("builtin", "basic", True, runtime_available=True),
        FetchProviderRuntimeStatus(
            "mcp",
            "basic",
            True,
            runtime_available=False,
            runtime_reason="mcp: missing modules: mcp",
        ),
        FetchProviderRuntimeStatus("site_crawler", "basic", True, runtime_available=True),
        FetchProviderRuntimeStatus(
            "jina_reader",
            "pro",
            False,
            edition_reason=(
                "fetch provider 'jina_reader' requires edition=pro, current edition=basic"
            ),
            runtime_reason=(
                "runtime not probed because fetch provider 'jina_reader' requires "
                "edition=pro, current edition=basic"
            ),
        ),
    )

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(
        "souwen.feature_matrix.fetch_provider_runtime_projection",
        lambda _edition: statuses,
    )

    mcp_server.create_server()
    tools = await created["server"]._list_tools()
    fetch_tool = next(tool for tool in tools if tool.name == "fetch_content")
    projection = fetch_tool.inputSchema["properties"]["provider"]["x-souwen-provider-projection"]

    assert projection["declared"] == ["builtin", "mcp", "site_crawler"]
    assert projection["available"] == ["builtin", "site_crawler"]
    assert [item["name"] for item in projection["unavailable"]] == ["mcp"]
    assert [item["name"] for item in projection["upgrade_required"]] == ["jina_reader"]
    assert "当前 edition 声明：builtin / mcp / site_crawler" in fetch_tool.description
    assert "当前 runtime 可导入：builtin / site_crawler" in fetch_tool.description
    assert "mcp: missing modules: mcp" in fetch_tool.description
    assert "当前可选" not in fetch_tool.description


@pytest.mark.asyncio
async def test_fetch_content_tool_schema_redacts_provider_loader_exception(monkeypatch):
    """MCP discovery must not expose arbitrary plugin loader exception text."""
    from souwen.registry.adapter import FETCH_DOMAIN, MethodSpec, SourceAdapter

    created: dict[str, _FakeServer] = {}
    secret = "postgresql://user:password@private.internal/db token=mcp-secret"

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    def failing_loader() -> type:
        raise RuntimeError(secret)

    broken = SourceAdapter(
        name="broken_fetch",
        domain=FETCH_DOMAIN,
        integration="open_api",
        description="broken fetch provider",
        config_field=None,
        client_loader=failing_loader,
        methods={"fetch": MethodSpec("fetch")},
        auth_requirement="none",
    )

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr("souwen.registry.fetch_providers", lambda: [broken])

    mcp_server.create_server()
    tools = await created["server"]._list_tools()
    fetch_tool = next(tool for tool in tools if tool.name == "fetch_content")
    projection = fetch_tool.inputSchema["properties"]["provider"]["x-souwen-provider-projection"]

    assert projection["providers"][0]["runtime_reason"] == (
        "broken_fetch: client loader unavailable"
    )
    serialized = json.dumps(projection)
    assert secret not in serialized
    assert "postgresql://" not in serialized
    assert "mcp-secret" not in fetch_tool.description


@pytest.mark.asyncio
async def test_fetch_content_tool_passes_multi_provider_strategy(monkeypatch):
    """MCP fetch_content 工具应透传 providers + strategy 到 fetch_content。"""
    from souwen.models import FetchResponse, FetchResult

    created: dict[str, _FakeServer] = {}
    captured: dict = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    async def fake_fetch_content(
        urls,
        providers=None,
        strategy="fallback",
        selector=None,
        start_index=0,
        max_length=None,
        respect_robots_txt=False,
    ):
        captured.update(
            {
                "urls": list(urls),
                "providers": list(providers) if providers else providers,
                "strategy": strategy,
                "selector": selector,
                "start_index": start_index,
                "max_length": max_length,
                "respect_robots_txt": respect_robots_txt,
            }
        )
        return FetchResponse(
            urls=list(urls),
            results=[
                FetchResult(
                    url=url,
                    final_url=url,
                    content="ok",
                    source=(providers[0] if providers else "builtin"),
                )
                for url in urls
            ],
            total=len(urls),
            total_ok=len(urls),
            total_failed=0,
            provider=None,
            providers=list(providers) if providers else ["builtin"],
            strategy=strategy,
        )

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)
    monkeypatch.setattr("souwen.web.fetch.fetch_content", fake_fetch_content)

    mcp_server.create_server()
    result = await created["server"]._call_tool(
        "fetch_content",
        {
            "urls": ["https://example.com"],
            "provider": "builtin",
            "providers": ["builtin", "jina_reader"],
            "strategy": "fanout",
            "selector": "article",
            "start_index": 10,
            "max_length": 500,
            "respect_robots_txt": True,
        },
    )

    assert captured == {
        "urls": ["https://example.com"],
        "providers": ["builtin", "jina_reader"],
        "strategy": "fanout",
        "selector": "article",
        "start_index": 10,
        "max_length": 500,
        "respect_robots_txt": True,
    }
    payload = json.loads(result[0].text)
    assert payload["providers"] == ["builtin", "jina_reader"]
    assert payload["strategy"] == "fanout"


@pytest.mark.asyncio
async def test_fetch_content_tool_normalizes_string_urls_and_providers(monkeypatch):
    """MCP 客户端误传字符串 urls/providers 时应归一化为单元素列表。"""
    from souwen.models import FetchResponse, FetchResult

    created: dict[str, _FakeServer] = {}
    captured: dict = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    async def fake_fetch_content(
        urls,
        providers=None,
        strategy="fallback",
        **_kwargs,
    ):
        captured.update(
            {
                "urls": list(urls),
                "providers": list(providers) if providers else providers,
                "strategy": strategy,
            }
        )
        return FetchResponse(
            urls=list(urls),
            results=[
                FetchResult(
                    url=url,
                    final_url=url,
                    content="ok",
                    source=(providers[0] if providers else "builtin"),
                )
                for url in urls
            ],
            total=len(urls),
            total_ok=len(urls),
            total_failed=0,
            provider=(providers[0] if providers and len(providers) == 1 else None),
            providers=list(providers) if providers else ["builtin"],
            strategy=strategy,
        )

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)
    monkeypatch.setattr("souwen.web.fetch.fetch_content", fake_fetch_content)

    mcp_server.create_server()
    result = await created["server"]._call_tool(
        "fetch_content",
        {
            "urls": "https://example.com",
            "providers": "builtin",
        },
    )

    assert captured == {
        "urls": ["https://example.com"],
        "providers": ["builtin"],
        "strategy": "fallback",
    }
    payload = json.loads(result[0].text)
    assert payload["provider"] == "builtin"
    assert payload["providers"] == ["builtin"]


@pytest.mark.asyncio
async def test_fetch_content_tool_rejects_invalid_provider_argument(monkeypatch):
    """MCP fetch_content 对非法 providers 类型返回清晰错误。"""
    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)

    mcp_server.create_server()
    result = await created["server"]._call_tool(
        "fetch_content",
        {
            "urls": ["https://example.com"],
            "providers": {"name": "builtin"},
        },
    )

    assert result[0].text.startswith("Error: ValueError:")
    assert "providers 必须是字符串或字符串列表" in result[0].text


@pytest.mark.asyncio
async def test_fetch_content_tool_reports_basic_edition_provider_error(monkeypatch):
    """MCP fetch_content 显式请求当前 edition 不支持的已知 provider 时返回 edition 错误。"""
    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)

    mcp_server.create_server()
    result = await created["server"]._call_tool(
        "fetch_content",
        {"urls": ["https://example.com"], "provider": "jina_reader"},
    )

    assert result[0].text.startswith("Error: EditionError:")
    assert "fetch provider 'jina_reader' requires edition=pro" in result[0].text
    assert "current edition=basic" in result[0].text


@pytest.mark.asyncio
async def test_create_server_bootstraps_configured_fetch_plugin(
    tmp_path,
    monkeypatch,
    clean_registry,
    clean_fetch_handlers,
):
    """stdio MCP 独立启动时也应加载 ``souwen.yaml`` 中声明的 fetch 插件。"""
    from souwen.models import FetchResponse, FetchResult
    from souwen.plugin import Plugin, _PLUGINS
    from souwen.registry.adapter import MethodSpec, SourceAdapter
    from souwen.registry.loader import lazy
    from souwen.web import fetch as web_fetch_mod
    from souwen.web.fetch import register_fetch_handler

    created: dict[str, _FakeServer] = {}

    def fake_server_factory(name: str):
        server = _FakeServer(name)
        created["server"] = server
        return server

    async def fake_handler(urls, timeout, **kwargs):
        results = [
            FetchResult(
                url=url,
                final_url=url,
                title="configured plugin",
                content="ok",
                source="mcp_configured_fetch",
            )
            for url in urls
        ]
        return FetchResponse(
            urls=list(urls),
            results=results,
            total=len(results),
            total_ok=len(results),
            total_failed=0,
            provider="mcp_configured_fetch",
        )

    def plugin_factory():
        register_fetch_handler("mcp_configured_fetch", fake_handler)
        return Plugin(
            name="mcp_configured_plugin",
            adapters=[
                SourceAdapter(
                    name="mcp_configured_fetch",
                    domain="fetch",
                    integration="scraper",
                    description="MCP configured fetch plugin",
                    config_field=None,
                    client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
                    methods={"fetch": MethodSpec("fetch")},
                    needs_config=False,
                )
            ],
        )

    (tmp_path / "souwen.yaml").write_text(
        'plugins:\n  - "souwen.integrations.mcp.server:_test_mcp_plugin_factory"\n',
        encoding="utf-8",
    )

    saved_plugins = dict(_PLUGINS)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOUWEN_PLUGIN_AUTOLOAD", "0")
    monkeypatch.setenv("SOUWEN_EDITION", "full")
    monkeypatch.setattr(mcp_server, "_test_mcp_plugin_factory", plugin_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Server", fake_server_factory, raising=False)
    monkeypatch.setattr(mcp_server, "Tool", _FakeTool, raising=False)
    monkeypatch.setattr(mcp_server, "TextContent", _FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "get_bilibili_tools", lambda: [])
    monkeypatch.setattr(mcp_server, "is_bilibili_tool", lambda name: False)
    monkeypatch.setattr(web_fetch_mod, "validate_fetch_url", lambda url: (True, "ok"))

    try:
        mcp_server._MCP_PLUGINS_BOOTSTRAPPED = False
        mcp_server.create_server()

        result = await created["server"]._call_tool(
            "fetch_content",
            {"urls": ["https://example.com"], "provider": "mcp_configured_fetch"},
        )
        payload = json.loads(result[0].text)
        assert payload["provider"] == "mcp_configured_fetch"
        assert payload["total_ok"] == 1
        assert payload["results"][0]["content"] == "ok"
    finally:
        _PLUGINS.clear()
        _PLUGINS.update(saved_plugins)
        mcp_server._MCP_PLUGINS_BOOTSTRAPPED = False
