"""YouTube 客户端单元测试。

覆盖 ``souwen.web.youtube.YouTubeClient`` 全功能路径。使用 ``pytest-httpx``
直接 mock HTTP 层（YouTube Data API v3 是纯 JSON）。
"""

from __future__ import annotations

import re

import pytest

from souwen.core.exceptions import ConfigError, ParseError, RateLimitError
from souwen.web.youtube import (
    VideoDetail,
    YouTubeClient,
    _parse_iso8601_duration,
)

# URL patterns for matching
_SEARCH_URL = re.compile(r"https://www\.googleapis\.com/youtube/v3/search")
_VIDEOS_URL = re.compile(r"https://www\.googleapis\.com/youtube/v3/videos")
_WATCH_URL = re.compile(r"https://www\.youtube\.com/watch")
_TIMEDTEXT_URL = re.compile(r"https://www\.youtube\.com/api/timedtext")


@pytest.fixture(autouse=True)
def _mock_api_key(monkeypatch):
    """默认让 resolve_api_key 返回测试 Key"""
    monkeypatch.setattr(
        "souwen.web.youtube.resolve_api_key",
        lambda *a, **kw: "test-youtube-key",
    )


def _sample_item(
    video_id="dQw4w9WgXcQ",
    title="Sample Video Title",
    description="Sample description text.",
    channel_title="Sample Channel",
    channel_id="UC1234567890",
    published_at="2024-01-01T00:00:00Z",
):
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


def _sample_response(items=None, next_page_token=None):
    items = items if items is not None else []
    resp = {
        "kind": "youtube#searchListResponse",
        "pageInfo": {"totalResults": len(items), "resultsPerPage": len(items)},
        "items": items,
    }
    if next_page_token:
        resp["nextPageToken"] = next_page_token
    return resp


def _sample_video_item(
    video_id="abc123",
    title="Test Video",
    view_count="1000000",
    like_count="50000",
    comment_count="3000",
    duration="PT4M13S",
):
    return {
        "kind": "youtube#video",
        "id": video_id,
        "snippet": {
            "title": title,
            "description": "A test video",
            "channelTitle": "TestChannel",
            "channelId": "UCtest",
            "publishedAt": "2024-01-01T00:00:00Z",
            "thumbnails": {"high": {"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}},
            "tags": ["test", "video"],
            "categoryId": "22",
        },
        "statistics": {
            "viewCount": view_count,
            "likeCount": like_count,
            "commentCount": comment_count,
        },
        "contentDetails": {"duration": duration},
    }


# ---------------------------------------------------------------------------
# ISO 8601 Duration Parser
# ---------------------------------------------------------------------------


class TestDurationParser:
    def test_minutes_seconds(self):
        assert _parse_iso8601_duration("PT4M13S") == 253

    def test_hours_minutes_seconds(self):
        assert _parse_iso8601_duration("PT1H30M5S") == 5405

    def test_seconds_only(self):
        assert _parse_iso8601_duration("PT45S") == 45

    def test_days(self):
        assert _parse_iso8601_duration("P1DT2H") == 93600

    def test_empty(self):
        assert _parse_iso8601_duration("") == 0

    def test_invalid(self):
        assert _parse_iso8601_duration("not_a_duration") == 0


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


async def test_no_api_key_raises_config_error(monkeypatch):
    monkeypatch.setattr("souwen.web.youtube.resolve_api_key", lambda *a, **kw: None)
    with pytest.raises(ConfigError):
        YouTubeClient()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def test_basic_search(httpx_mock):
    httpx_mock.add_response(
        url=_SEARCH_URL,
        json=_sample_response(
            items=[
                _sample_item(
                    video_id="abc123",
                    title="Python Tutorial",
                    description="Learn Python",
                    channel_title="DevCh",
                    channel_id="UCdev",
                    published_at="2024-05-01T12:00:00Z",
                ),
                _sample_item(video_id="xyz789", title="Async Python", description="asyncio"),
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
    assert first.snippet == "Learn Python"
    assert first.engine == "youtube"
    assert first.raw["channelTitle"] == "DevCh"


async def test_empty_results(httpx_mock):
    httpx_mock.add_response(url=_SEARCH_URL, json=_sample_response(items=[]))
    async with YouTubeClient() as client:
        resp = await client.search("zzznoresult")
    assert resp.results == []
    assert resp.total_results == 0


async def test_pagination(httpx_mock):
    page1 = [_sample_item(video_id=f"vid{i}", title=f"V{i}") for i in range(50)]
    httpx_mock.add_response(
        url=_SEARCH_URL,
        json=_sample_response(items=page1, next_page_token="PAGE2"),
    )
    page2 = [_sample_item(video_id=f"vid{i}", title=f"V{i}") for i in range(50, 70)]
    httpx_mock.add_response(url=_SEARCH_URL, json=_sample_response(items=page2))

    async with YouTubeClient() as client:
        resp = await client.search("paginate", max_results=60)
    assert len(resp.results) == 60


async def test_search_filters(httpx_mock):
    httpx_mock.add_response(url=_SEARCH_URL, json=_sample_response(items=[_sample_item()]))
    async with YouTubeClient() as client:
        await client.search(
            "test",
            published_after="2024-01-01T00:00:00Z",
            region_code="US",
            relevance_language="en",
            channel_id="UCtest",
        )
    req = httpx_mock.get_requests()[0]
    url_str = str(req.url)
    assert "regionCode=US" in url_str
    assert "relevanceLanguage=en" in url_str
    assert "channelId=UCtest" in url_str


async def test_search_with_enrich(httpx_mock):
    httpx_mock.add_response(
        url=_SEARCH_URL,
        json=_sample_response(items=[_sample_item(video_id="enr1", title="Enrich")]),
    )
    httpx_mock.add_response(
        url=_VIDEOS_URL,
        json={
            "items": [
                {
                    "id": "enr1",
                    "statistics": {"viewCount": "999", "likeCount": "100", "commentCount": "10"},
                    "contentDetails": {"duration": "PT5M30S"},
                }
            ]
        },
    )
    async with YouTubeClient() as client:
        resp = await client.search("test", enrich=True)
    assert resp.results[0].raw["viewCount"] == 999
    assert resp.results[0].raw["durationSeconds"] == 330


async def test_enrich_failure_returns_original(httpx_mock):
    httpx_mock.add_response(
        url=_SEARCH_URL,
        json=_sample_response(items=[_sample_item(video_id="f1", title="Fail")]),
    )
    httpx_mock.add_response(url=_VIDEOS_URL, status_code=500)
    async with YouTubeClient() as client:
        resp = await client.search("test", enrich=True)
    assert len(resp.results) == 1
    assert resp.results[0].title == "Fail"


async def test_max_results_capped(httpx_mock):
    httpx_mock.add_response(url=_SEARCH_URL, json=_sample_response(items=[_sample_item()]))
    async with YouTubeClient() as client:
        resp = await client.search("test", max_results=999)
    assert len(resp.results) == 1


async def test_order_param(httpx_mock):
    httpx_mock.add_response(url=_SEARCH_URL, json=_sample_response(items=[_sample_item()]))
    async with YouTubeClient() as client:
        await client.search("q", order="viewCount")
    assert "order=viewCount" in str(httpx_mock.get_requests()[0].url)


async def test_url_construction(httpx_mock):
    httpx_mock.add_response(
        url=_SEARCH_URL,
        json=_sample_response(items=[_sample_item(video_id="MY_VID", title="t")]),
    )
    async with YouTubeClient() as client:
        resp = await client.search("url")
    assert resp.results[0].url == "https://www.youtube.com/watch?v=MY_VID"


async def test_snippet_truncation(httpx_mock):
    httpx_mock.add_response(
        url=_SEARCH_URL,
        json=_sample_response(items=[_sample_item(description="x" * 1000)]),
    )
    async with YouTubeClient() as client:
        resp = await client.search("long")
    assert len(resp.results[0].snippet) == 300


async def test_parse_error_on_bad_json(httpx_mock):
    httpx_mock.add_response(
        url=_SEARCH_URL,
        content=b"<html>not json</html>",
        headers={"Content-Type": "text/html"},
    )
    async with YouTubeClient() as client:
        with pytest.raises(ParseError):
            await client.search("bad")


async def test_invalid_order_raises_value_error():
    async with YouTubeClient() as client:
        with pytest.raises(ValueError):
            await client.search("q", order="invalid")


# ---------------------------------------------------------------------------
# Quota exceeded
# ---------------------------------------------------------------------------


async def test_quota_exceeded_raises_rate_limit_error(httpx_mock):
    httpx_mock.add_response(
        url=_SEARCH_URL,
        status_code=403,
        json={
            "error": {
                "errors": [{"reason": "quotaExceeded", "domain": "youtube.quota"}],
                "code": 403,
                "message": "quota exceeded",
            }
        },
    )
    async with YouTubeClient() as client:
        with pytest.raises(RateLimitError, match="配额已用尽"):
            await client.search("test")


# ---------------------------------------------------------------------------
# Trending
# ---------------------------------------------------------------------------


async def test_get_trending(httpx_mock):
    httpx_mock.add_response(
        url=_VIDEOS_URL,
        json={
            "items": [
                {
                    "id": "trend1",
                    "snippet": {
                        "title": "Trending",
                        "description": "pop",
                        "channelTitle": "Ch",
                        "channelId": "UC1",
                        "publishedAt": "2024-06-01T00:00:00Z",
                        "thumbnails": {},
                    },
                    "statistics": {
                        "viewCount": "5000000",
                        "likeCount": "200000",
                        "commentCount": "15000",
                    },
                }
            ]
        },
    )
    async with YouTubeClient() as client:
        resp = await client.get_trending(region_code="US", category_id="20")
    assert resp.query == "trending:US:20"
    assert resp.results[0].title == "Trending"
    assert resp.results[0].raw["viewCount"] == 5000000
    url_str = str(httpx_mock.get_requests()[0].url)
    assert "chart=mostPopular" in url_str
    assert "regionCode=US" in url_str


# ---------------------------------------------------------------------------
# Video Details
# ---------------------------------------------------------------------------


async def test_get_video_details(httpx_mock):
    httpx_mock.add_response(
        url=_VIDEOS_URL,
        json={"items": [_sample_video_item(video_id="d1", title="Detail")]},
    )
    async with YouTubeClient() as client:
        details = await client.get_video_details(["d1"])
    assert len(details) == 1
    d = details[0]
    assert isinstance(d, VideoDetail)
    assert d.video_id == "d1"
    assert d.view_count == 1000000
    assert d.duration_seconds == 253
    assert d.tags == ["test", "video"]


async def test_get_video_details_dedup(httpx_mock):
    httpx_mock.add_response(
        url=_VIDEOS_URL,
        json={"items": [_sample_video_item(video_id="dup1")]},
    )
    async with YouTubeClient() as client:
        details = await client.get_video_details(["dup1", "dup1", "dup1"])
    assert len(details) == 1


async def test_get_video_details_missing(httpx_mock):
    httpx_mock.add_response(
        url=_VIDEOS_URL,
        json={"items": [_sample_video_item(video_id="exists")]},
    )
    async with YouTubeClient() as client:
        details = await client.get_video_details(["exists", "gone"])
    assert len(details) == 1
    assert details[0].video_id == "exists"


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


async def test_get_transcript_success(httpx_mock):
    watch_html = (
        "<html><script>"
        '"captionTracks":[{"baseUrl":"https://www.youtube.com/api/timedtext?v=t&lang=en",'
        '"languageCode":"en"}]'
        "</script></html>"
    )
    httpx_mock.add_response(url=_WATCH_URL, text=watch_html)
    caption_xml = (
        '<?xml version="1.0"?><transcript>'
        '<text start="0" dur="5">Hello world</text>'
        '<text start="5" dur="3">Testing</text>'
        "</transcript>"
    )
    httpx_mock.add_response(url=_TIMEDTEXT_URL, text=caption_xml)

    async with YouTubeClient() as client:
        transcript = await client.get_transcript("test123", lang="en")
    assert transcript is not None
    assert "Hello world" in transcript
    assert "Testing" in transcript


async def test_get_transcript_no_captions(httpx_mock):
    httpx_mock.add_response(url=_WATCH_URL, text="<html>no captions</html>")
    async with YouTubeClient() as client:
        transcript = await client.get_transcript("nocap")
    assert transcript is None


async def test_get_transcript_network_error(httpx_mock):
    httpx_mock.add_exception(Exception("fail"), url=_WATCH_URL)
    async with YouTubeClient() as client:
        transcript = await client.get_transcript("err")
    assert transcript is None
