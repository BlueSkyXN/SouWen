"""Perplexity 搜索客户端单元测试。

覆盖 ``souwen.providers.runtime_clients.web.perplexity.PerplexityClient`` 的请求头。

测试清单：
- ``test_search_sends_integration_header``：默认发送 X-Pplx-Integration: souwen
- ``test_channel_integration_header_wins``：频道配置的同名请求头（大小写不敏感）优先且不重复
"""

from __future__ import annotations

from souwen.common_runtime.provider_support import http_client as http_client_module
from souwen.config import SouWenConfig
from souwen.providers.runtime_clients.web.perplexity import PerplexityClient

_CHAT_URL = "https://api.perplexity.ai/v1/chat/completions"
_RESPONSE = {"choices": [{"message": {"content": "answer"}}]}


async def test_search_sends_integration_header(httpx_mock):
    """默认发送 X-Pplx-Integration: souwen"""
    httpx_mock.add_response(url=_CHAT_URL, json=_RESPONSE)

    async with PerplexityClient(api_key="pplx-test") as client:
        await client.search("query")

    req = httpx_mock.get_requests()[0]
    assert req.headers.get("authorization") == "Bearer pplx-test"
    assert req.headers.get_list("x-pplx-integration") == ["souwen"]


async def test_channel_integration_header_wins(httpx_mock, monkeypatch):
    """频道配置的同名请求头（大小写不敏感）优先且不重复"""
    config = SouWenConfig(sources={"perplexity": {"headers": {"x-pplx-integration": "custom"}}})
    monkeypatch.setattr(http_client_module, "get_config", lambda: config)
    httpx_mock.add_response(url=_CHAT_URL, json=_RESPONSE)

    async with PerplexityClient(api_key="pplx-test") as client:
        await client.search("query")

    req = httpx_mock.get_requests()[0]
    assert req.headers.get_list("x-pplx-integration") == ["custom"]
