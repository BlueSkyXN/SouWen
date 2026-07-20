"""YouTube route request-boundary tests."""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from souwen.core.exceptions import ConfigError
from souwen.models import WebSearchResponse, WebSearchResult
from souwen.web.youtube import VideoDetail


@pytest.fixture(autouse=True)
def isolated_search_limiter(monkeypatch):
    from souwen.server import limiter as limiter_mod

    monkeypatch.setattr(
        limiter_mod,
        "_search_limiter",
        limiter_mod.InMemoryRateLimiter(max_requests=60, window_seconds=60),
    )


@pytest.fixture()
def client():
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def stub_youtube_client(monkeypatch):
    """Replace YouTubeClient with an in-memory fake and record route inputs."""
    calls: list[dict] = []

    class FakeYouTubeClient:
        async def get_trending(
            self,
            region_code="US",
            video_category_id=None,
            max_results=20,
        ):
            calls.append(
                {
                    "method": "trending",
                    "region_code": region_code,
                    "video_category_id": video_category_id,
                    "max_results": max_results,
                }
            )
            return WebSearchResponse(
                query="trending",
                source="youtube",
                results=[
                    WebSearchResult(
                        source="youtube",
                        title="Example",
                        url="https://www.youtube.com/watch?v=abc123",
                        snippet="Example",
                        engine="youtube",
                    )
                ],
                total_results=1,
            )

        async def get_video_details(self, video_ids):
            calls.append({"method": "details", "video_ids": list(video_ids)})
            return [
                VideoDetail(
                    video_id=video_ids[0],
                    title="Example",
                    channel_title="Example Channel",
                )
            ]

        async def get_transcript(self, video_id, lang="en"):
            calls.append({"method": "transcript", "video_id": video_id, "lang": lang})
            return "caption text"

    monkeypatch.setattr("souwen.web.youtube.YouTubeClient", FakeYouTubeClient)
    return calls


def test_youtube_trending_region_and_category_are_normalized(client, stub_youtube_client):
    """Trending route should trim region/category and uppercase region codes."""
    resp = client.get(
        "/api/v1/youtube/trending",
        params={"region": " us ", "category": " 10 ", "max_results": 3},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["region"] == "US"
    assert body["category"] == "10"
    assert stub_youtube_client == [
        {
            "method": "trending",
            "region_code": "US",
            "video_category_id": "10",
            "max_results": 3,
        }
    ]


def test_youtube_trending_blank_region_returns_422(client, stub_youtube_client):
    """Blank region query values should be rejected before calling YouTubeClient."""
    resp = client.get("/api/v1/youtube/trending", params={"region": "   "})

    assert resp.status_code == 422
    assert stub_youtube_client == []


def test_youtube_trending_blank_category_behaves_like_omitted(client, stub_youtube_client):
    """Blank category is optional and should be normalized to no category filter."""
    resp = client.get("/api/v1/youtube/trending", params={"category": "   "})

    assert resp.status_code == 200, resp.text
    assert resp.json()["category"] == ""
    assert stub_youtube_client == [
        {
            "method": "trending",
            "region_code": "US",
            "video_category_id": None,
            "max_results": 20,
        }
    ]


def test_youtube_video_detail_blank_video_id_returns_422(client, stub_youtube_client):
    """Blank path video_id should be rejected before calling YouTubeClient."""
    resp = client.get("/api/v1/youtube/video/%20%20%20")

    assert resp.status_code == 422
    assert stub_youtube_client == []


def test_youtube_video_detail_video_id_is_normalized(client, stub_youtube_client):
    """Video detail route should trim path video_id before querying details."""
    resp = client.get("/api/v1/youtube/video/%20abc123%20")

    assert resp.status_code == 200, resp.text
    assert resp.json()["video_ids"] == ["abc123"]
    assert stub_youtube_client == [{"method": "details", "video_ids": ["abc123"]}]


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/v1/youtube/transcript/%20%20%20", {}),
        ("/api/v1/youtube/transcript/abc123", {"lang": "   "}),
    ],
)
def test_youtube_transcript_blank_inputs_return_422(
    client,
    stub_youtube_client,
    path,
    params,
):
    """Transcript route should reject blank video_id/lang before calling YouTubeClient."""
    resp = client.get(path, params=params)

    assert resp.status_code == 422
    assert stub_youtube_client == []


def test_youtube_transcript_inputs_are_normalized(client, stub_youtube_client):
    """Transcript route should trim path video_id and lang query values."""
    resp = client.get("/api/v1/youtube/transcript/%20abc123%20", params={"lang": " zh "})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["video_id"] == "abc123"
    assert body["lang"] == "zh"
    assert body["text"] == "caption text"
    assert stub_youtube_client == [{"method": "transcript", "video_id": "abc123", "lang": "zh"}]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/youtube/trending",
        "/api/v1/youtube/video/abc123",
        "/api/v1/youtube/transcript/abc123",
    ],
)
def test_youtube_config_error_detail_redacts_secrets(client, monkeypatch, path):
    class FakeYouTubeClient:
        def __init__(self):
            raise ConfigError(
                "youtube_api_key token=yt-secret",
                "YouTube Cookie: sid=session-secret",
                "https://yt.example/cb?apiKey=url-secret&safe=1",
            )

    monkeypatch.setattr("souwen.web.youtube.YouTubeClient", FakeYouTubeClient)

    resp = client.get(path)

    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "yt-secret" not in detail
    assert "session-secret" not in detail
    assert "url-secret" not in detail
    assert "token:***" in detail
    assert "Cookie:***" in detail
    assert "apiKey=***" in detail
    assert "safe=1" in detail
