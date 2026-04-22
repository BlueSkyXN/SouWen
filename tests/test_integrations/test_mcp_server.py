from __future__ import annotations

import importlib

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
        mcp_server._DEFAULT_PAPER_SOURCES_LABEL
    )

    result = await server._call_tool("search_papers", {"query": "foo"})
    assert captured == {"query": "foo", "sources": None, "per_page": 5}
    assert len(result) == 1
    assert result[0].text == "[]"
