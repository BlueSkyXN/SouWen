"""YouTube 搜索客户端单元测试。

覆盖 ``souwen.web.youtube.YouTubeClient`` 视频搜索路径。使用 ``pytest-httpx``
直接 mock HTTP 层（YouTube Data API v3 是纯 JSON）。

测试清单：
- ``test_no_api_key_raises_config_error``：未配置 Key 时初始化抛 ConfigError
- ``test_basic_search``：正常搜索：返回结果且字段映射正确
- ``test_empty_results``：空结果（items=[]）返回空列表不崩溃
- ``test_max_results_capped_at_50``：max_results > 50 时 maxResults 参数被截断为 50
- ``test_order_param``：order 参数被透传到 URL
- ``test_url_construction``：YouTube 视频 URL 正确拼接 watch?v= 形式
- ``test_snippet_truncation``：超长描述截断到 300 字符
- ``test_parse_error_on_bad_json``：非 JSON 响应抛 ParseError
"""

from __future__ import annotations

import pytest

from souwen.exceptions import ConfigError, ParseError
from souwen.web.youtube import YouTubeClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_api_key(monkeypatch):
    """默认让 resolve_api_key 返回测试 Key，避免依赖真实环境变量"""
    monkeypatch.setattr(
        "souwen.web.youtube.resolve_api_key",
        lambda *a, **kw: "test-youtube-key",
    )


def _sample_item(
    video_id: str = "dQw4w9WgXcQ",
    title: str = "Sample Video Title",
    description: str = "Sample description text.",
    channel_title: str = "Sample Channel",
    channel_id: str = "UC1234567890",
    published_at: str = "2024-01-01T00:00:00Z",
) -> dict:
    """构造一条 YouTube search.list item"""
    return {
        "kind": "youtube#searchResult",
        "id": {"kind": "youtube#video", "videoId": video_id},
        "snippet": {
            "title": title,
            "description": description,
            "channelTitle": channel_title,
            "channelId": channel_id,
            "publishedAt": published_at,
            "thumbnails": {"default": {"url": f"https://i.ytimg.com/vi/{video_id}/default.jpg"}},
        },
    }


def _sample_response(items: list[dict] | None = None) -> dict:
    """构造 YouTube /youtube/v3/search 风格的响应"""
    items = items if items is not None else []
    return {
        "kind": "youtube#searchListResponse",
        "pageInfo": {"totalResults": len(items), "resultsPerPage": len(items)},
        "items": items,
    }


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


async def test_no_api_key_raises_config_error(monkeypatch):
    """未配置 Key 时初始化抛 ConfigError"""
    monkeypatch.setattr("souwen.web.youtube.resolve_api_key", lambda *a, **kw: None)
    with pytest.raises(ConfigError):
        YouTubeClient()


# ---------------------------------------------------------------------------
# search tests
# ---------------------------------------------------------------------------


async def test_basic_search(httpx_mock):
    """正常搜索：返回结果并映射字段"""
    httpx_mock.add_response(
        url=(
            "https://www.googleapis.com/youtube/v3/search"
            "?part=snippet&q=python&type=video&maxResults=10&order=relevance"
            "&key=test-youtube-key"
        ),
        json=_sample_response(
            items=[
                _sample_item(
                    video_id="abc123",
                    title="Python Tutorial",
                    description="Learn Python in 10 minutes",
                    channel_title="DevChannel",
                    channel_id="UCdev",
                    published_at="2024-05-01T12:00:00Z",
                ),
                _sample_item(
                    video_id="xyz789",
                    title="Async Python",
                    description="asyncio basics",
                ),
            ]
        ),
    )

    async with YouTubeClient() as client:
        resp = await client.search("python", max_results=10)

    assert resp.query == "python"
    assert resp.source.value == "web_youtube"
    assert len(resp.results) == 2

    first = resp.results[0]
    assert first.title == "Python Tutorial"
    assert first.url == "https://www.youtube.com/watch?v=abc123"
    assert first.snippet == "Learn Python in 10 minutes"
    assert first.engine == "youtube"
    assert first.source.value == "web_youtube"
    assert first.raw["channelTitle"] == "DevChannel"
    assert first.raw["channelId"] == "UCdev"
    assert first.raw["publishedAt"] == "2024-05-01T12:00:00Z"
    assert "default" in first.raw["thumbnails"]


async def test_empty_results(httpx_mock):
    """空结果返回空列表，不抛异常"""
    httpx_mock.add_response(
        url=(
            "https://www.googleapis.com/youtube/v3/search"
            "?part=snippet&q=zzznoresult&type=video&maxResults=10&order=relevance"
            "&key=test-youtube-key"
        ),
        json=_sample_response(items=[]),
    )

    async with YouTubeClient() as client:
        resp = await client.search("zzznoresult")

    assert resp.results == []
    assert resp.total_results == 0


async def test_max_results_capped_at_50(httpx_mock):
    """max_results > 50 时 API maxResults 参数被截断为 50"""
    httpx_mock.add_response(
        url=(
            "https://www.googleapis.com/youtube/v3/search"
            "?part=snippet&q=many&type=video&maxResults=50&order=relevance"
            "&key=test-youtube-key"
        ),
        json=_sample_response(
            items=[_sample_item(video_id=f"vid{i}", title=f"Video {i}") for i in range(3)]
        ),
    )

    async with YouTubeClient() as client:
        # 即便传入 100，URL 中应该出现 maxResults=50（由 httpx_mock 严格匹配）
        resp = await client.search("many", max_results=100)

    assert len(resp.results) == 3


async def test_order_param(httpx_mock):
    """order 参数被透传到查询字符串"""
    httpx_mock.add_response(
        url=(
            "https://www.googleapis.com/youtube/v3/search"
            "?part=snippet&q=q&type=video&maxResults=10&order=viewCount"
            "&key=test-youtube-key"
        ),
        json=_sample_response(items=[_sample_item()]),
    )

    async with YouTubeClient() as client:
        resp = await client.search("q", order="viewCount")

    assert len(resp.results) == 1


async def test_url_construction(httpx_mock):
    """YouTube 视频 URL 拼接为 https://www.youtube.com/watch?v={videoId}"""
    httpx_mock.add_response(
        url=(
            "https://www.googleapis.com/youtube/v3/search"
            "?part=snippet&q=url&type=video&maxResults=10&order=relevance"
            "&key=test-youtube-key"
        ),
        json=_sample_response(items=[_sample_item(video_id="MY_VIDEO_ID", title="t")]),
    )

    async with YouTubeClient() as client:
        resp = await client.search("url")

    assert resp.results[0].url == "https://www.youtube.com/watch?v=MY_VIDEO_ID"


async def test_snippet_truncation(httpx_mock):
    """超长描述被截断到 300 字符"""
    long_desc = "x" * 1000
    httpx_mock.add_response(
        url=(
            "https://www.googleapis.com/youtube/v3/search"
            "?part=snippet&q=long&type=video&maxResults=10&order=relevance"
            "&key=test-youtube-key"
        ),
        json=_sample_response(items=[_sample_item(description=long_desc)]),
    )

    async with YouTubeClient() as client:
        resp = await client.search("long")

    assert len(resp.results[0].snippet) == 300
    assert resp.results[0].snippet == "x" * 300


async def test_parse_error_on_bad_json(httpx_mock):
    """非 JSON 响应抛 ParseError"""
    httpx_mock.add_response(
        url=(
            "https://www.googleapis.com/youtube/v3/search"
            "?part=snippet&q=bad&type=video&maxResults=10&order=relevance"
            "&key=test-youtube-key"
        ),
        content=b"<html>not json</html>",
        headers={"Content-Type": "text/html"},
    )

    async with YouTubeClient() as client:
        with pytest.raises(ParseError):
            await client.search("bad")


async def test_invalid_order_raises_value_error():
    """非法 order 抛 ValueError（参数校验路径）"""
    async with YouTubeClient() as client:
        with pytest.raises(ValueError):
            await client.search("q", order="not_a_real_order")
