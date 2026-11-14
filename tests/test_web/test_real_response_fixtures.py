"""真实响应夹具驱动的解析测试（SPEC 7 / P4-2）。

夹具录制自真实上游（2026-11-14，录制脚本保存在
local/20261111-项目瘦身/scripts/），脱敏截取后放 tests/fixtures/。
这些测试替换等价的"手写假响应"测试：解析链消费真实 HTML/JSON 形态。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from souwen.providers.runtime_clients.web.baidu import BaiduClient
from souwen.providers.runtime_clients.web.juejin import JuejinClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _html_response(body: str) -> MagicMock:
    response = MagicMock()
    response.text = body
    response.status_code = 200
    return response


class TestBaiduRealFixture:
    """百度结果页 HTML 解析（真实响应，截取结果容器区块）。"""

    @pytest.mark.asyncio
    async def test_parses_real_result_container(self):
        fixture = _load("baidu_search.html.json")
        client = BaiduClient(follow_redirects=False)
        client._fetch = AsyncMock(return_value=_html_response(fixture["body"]))

        response = await client.search("python asyncio tutorial", max_results=5)

        assert response.source == "baidu"
        assert 1 <= len(response.results) <= 5
        first = response.results[0]
        assert first.title.strip()
        assert first.url.startswith("http")
        # 真实页面的标题不应携带 HTML 标签（解析链剥掉了 <em> 等）
        assert "<" not in first.title

    @pytest.mark.asyncio
    async def test_max_results_bounds_real_page(self):
        fixture = _load("baidu_search.html.json")
        client = BaiduClient(follow_redirects=False)
        client._fetch = AsyncMock(return_value=_html_response(fixture["body"]))

        response = await client.search("python", max_results=2)

        assert len(response.results) <= 2


class TestJuejinRealFixture:
    """掘金搜索 API JSON 解析（真实响应）。"""

    @pytest.mark.asyncio
    async def test_parses_real_article_payload(self):
        fixture = _load("juejin_search_api.json")
        client = JuejinClient()

        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.json.return_value = fixture["payload"]
        client._fetch = AsyncMock(return_value=response_mock)

        response = await client.search("python asyncio", max_results=5)

        assert response.source == "juejin"
        assert 1 <= len(response.results) <= 5
        first = response.results[0]
        assert first.title.strip()
        assert "juejin.cn/post/" in first.url
        # 真实响应的 snippet 是富文本，解析链应产出纯文本
        assert "<" not in (first.snippet or "")
