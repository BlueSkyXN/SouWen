from __future__ import annotations

import importlib
import json

import pytest

from souwen.integrations.mcp import server as mcp_server


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
    assert paper_tool.inputSchema["properties"]["sources"]["description"].endswith(
        mcp_server._default_paper_sources_label()
    )

    result = await server._call_tool("search_papers", {"query": "foo"})
    assert captured == {"query": "foo", "sources": None, "per_page": 5}
    assert len(result) == 1
    assert result[0].text == "[]"


@pytest.mark.asyncio
async def test_fetch_content_tool_schema_mentions_scrapling(monkeypatch):
    """MCP fetch_content 工具说明应同步 fetch provider 能力。"""
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
    assert "builtin / scrapling" in fetch_tool.description
    assert "scrapling" in props["provider"]["description"]
    assert "builtin / scrapling" in props["selector"]["description"]
    assert (
        props["respect_robots_txt"]["description"] == "是否遵守 robots.txt（provider 支持时生效）"
    )


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
