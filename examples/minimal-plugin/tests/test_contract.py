"""验证示例插件满足 SouWen 插件对接规范。"""

import pytest
from souwen.registry.adapter import SourceAdapter
from souwen_example_plugin import plugin
from souwen_example_plugin.client import EchoClient


class TestPluginContract:
    def test_plugin_is_source_adapter(self):
        assert isinstance(plugin, SourceAdapter)

    def test_required_fields(self):
        assert plugin.name == "example_echo"
        assert plugin.domain == "fetch"
        assert plugin.integration in ("open_api", "scraper", "official_api", "self_hosted")
        assert plugin.description
        assert plugin.client_loader is not None
        assert "fetch" in plugin.methods

    def test_client_loader_resolves(self):
        cls = plugin.client_loader()
        assert cls is EchoClient


class TestClientContract:
    @pytest.fixture
    def client(self):
        return EchoClient()

    @pytest.mark.asyncio
    async def test_async_context_manager(self, client):
        async with client as c:
            assert c is client

    @pytest.mark.asyncio
    async def test_fetch_returns_response(self, client):
        from souwen.models import FetchResponse
        resp = await client.fetch(["https://example.com"], timeout=10)
        assert isinstance(resp, FetchResponse)
        assert resp.total == 1
        assert resp.total_ok == 1
        assert resp.results[0].url == "https://example.com"
        assert resp.results[0].error is None


class TestHandlerContract:
    def test_handler_is_async(self):
        import asyncio
        from souwen_example_plugin.handler import example_echo_handler
        assert asyncio.iscoroutinefunction(example_echo_handler)

    @pytest.mark.asyncio
    async def test_handler_returns_fetch_response(self):
        from souwen.models import FetchResponse
        from souwen_example_plugin.handler import example_echo_handler
        resp = await example_echo_handler(["https://example.com"])
        assert isinstance(resp, FetchResponse)
