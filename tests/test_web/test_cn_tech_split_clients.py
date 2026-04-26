from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from souwen.models import SourceType, WebSearchResponse, WebSearchResult
from souwen.web.coolapk import CoolapkClient
from souwen.web.hostloc import HostLocClient
from souwen.web.nodeseek import NodeSeekClient
from souwen.web.v2ex import V2EXClient
from souwen.web.xiaohongshu import XiaohongshuClient


def _mock_ddg_response(query: str, domain: str) -> WebSearchResponse:
    return WebSearchResponse(
        query=query,
        source=SourceType.WEB_DUCKDUCKGO,
        total_results=1,
        results=[
            WebSearchResult(
                source=SourceType.WEB_DUCKDUCKGO,
                title=f"{domain} post",
                url=f"https://{domain}/t/1",
                snippet="snippet",
                engine="duckduckgo",
            )
        ],
    )


@pytest.mark.parametrize(
    ("client_cls", "source", "engine", "domain"),
    [
        (NodeSeekClient, SourceType.WEB_NODESEEK, "nodeseek", "nodeseek.com"),
        (HostLocClient, SourceType.WEB_HOSTLOC, "hostloc", "hostloc.com"),
        (V2EXClient, SourceType.WEB_V2EX, "v2ex", "v2ex.com"),
        (CoolapkClient, SourceType.WEB_COOLAPK, "coolapk", "coolapk.com"),
        (XiaohongshuClient, SourceType.WEB_XIAOHONGSHU, "xiaohongshu", "xiaohongshu.com"),
    ],
)
@pytest.mark.asyncio
async def test_cn_tech_split_client_maps_ddg_result(client_cls, source, engine, domain):
    client = client_cls()
    ddg = AsyncMock()
    ddg.search = AsyncMock(return_value=_mock_ddg_response("site query", domain))
    client._ddg_client = ddg

    resp = await client.search("python", max_results=3)

    assert resp.source == source
    assert resp.total_results == 1
    assert resp.results[0].source == source
    assert resp.results[0].engine == engine
    assert resp.results[0].url == f"https://{domain}/t/1"
    ddg.search.assert_awaited_once_with(f"site:{domain} python", max_results=3, max_pages=1)


@pytest.mark.parametrize(
    "client_cls,source",
    [
        (NodeSeekClient, SourceType.WEB_NODESEEK),
        (HostLocClient, SourceType.WEB_HOSTLOC),
        (V2EXClient, SourceType.WEB_V2EX),
        (CoolapkClient, SourceType.WEB_COOLAPK),
        (XiaohongshuClient, SourceType.WEB_XIAOHONGSHU),
    ],
)
@pytest.mark.asyncio
async def test_cn_tech_split_client_handles_ddg_error(client_cls, source):
    client = client_cls()
    ddg = AsyncMock()
    ddg.search = AsyncMock(side_effect=RuntimeError("ddg error"))
    client._ddg_client = ddg

    resp = await client.search("python")

    assert resp.source == source
    assert resp.total_results == 0
    assert resp.results == []
