"""Bilibili public route validation tests."""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not installed", allow_module_level=True)

from souwen.models import WebSearchResponse, WebSearchResult
from souwen.web.bilibili._errors import (
    BilibiliAuthRequired,
    BilibiliError,
    BilibiliNotFound,
    BilibiliRateLimited,
    BilibiliRiskControl,
)
from souwen.web.bilibili.models import (
    BilibiliArticleResult,
    BilibiliSearchUserItem,
    BilibiliVideoDetail,
)


@pytest.fixture(autouse=True)
def _isolate_config_files(monkeypatch, tmp_path):
    """Server route tests must not read the developer machine config."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("SOUWEN_PLUGIN_AUTOLOAD", "0")
    for key in (
        "SOUWEN_API_PASSWORD",
        "SOUWEN_VISITOR_PASSWORD",
        "SOUWEN_USER_PASSWORD",
        "SOUWEN_ADMIN_PASSWORD",
        "SOUWEN_ADMIN_OPEN",
        "SOUWEN_GUEST_ENABLED",
        "SOUWEN_SOURCES",
        "SOUWEN_TRUSTED_PROXIES",
    ):
        monkeypatch.delenv(key, raising=False)
    from souwen.config import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture()
def client():
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


def _patch_bilibili_client(monkeypatch, fake_cls: type) -> None:
    from souwen.server.routes import bilibili as bilibili_route

    monkeypatch.setattr(bilibili_route, "BilibiliClient", fake_cls)


class _UnexpectedBilibiliClient:
    def __init__(self):
        raise AssertionError("BilibiliClient should not be instantiated")


@pytest.mark.parametrize(
    ("endpoint", "params"),
    [
        ("/api/v1/bilibili/search", {"keyword": "   "}),
        ("/api/v1/bilibili/search/users", {"keyword": "   "}),
        ("/api/v1/bilibili/search/articles", {"keyword": "   "}),
        ("/api/v1/bilibili/video/%20%20%20", {}),
    ],
)
def test_bilibili_blank_required_text_is_rejected(client, monkeypatch, endpoint, params):
    """Bilibili route required text fields must reject whitespace-only values."""
    _patch_bilibili_client(monkeypatch, _UnexpectedBilibiliClient)

    resp = client.get(endpoint, params=params)

    assert resp.status_code == 422


def test_bilibili_video_keyword_is_trimmed_before_search(client, monkeypatch):
    captured: dict[str, str] = {}

    class FakeBilibiliClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def search(self, keyword, max_results=20, order="totalrank"):
            captured["keyword"] = keyword
            captured["order"] = order
            return WebSearchResponse(
                query=keyword,
                source="bilibili",
                total_results=1,
                results=[
                    WebSearchResult(
                        source="bilibili",
                        title="Graph RAG",
                        url="https://www.bilibili.com/video/BV1xx411c7mD",
                        snippet="demo",
                        engine="bilibili",
                        raw={
                            "bvid": "BV1xx411c7mD",
                            "aid": 123,
                            "author": "tester",
                            "mid": 456,
                            "play": 1000,
                            "video_review": 20,
                            "duration": "01:23",
                            "pic": "//i0.hdslb.com/demo.jpg",
                            "pubdate": 1710000000,
                            "tag": "AI",
                        },
                    )
                ],
            )

    _patch_bilibili_client(monkeypatch, FakeBilibiliClient)

    resp = client.get(
        "/api/v1/bilibili/search",
        params={"keyword": "  graph rag  ", "order": "pubdate"},
    )

    assert resp.status_code == 200
    assert captured == {"keyword": "graph rag", "order": "pubdate"}
    body = resp.json()
    assert body["keyword"] == "graph rag"
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["order"] == "pubdate"
    assert body["results"][0]["bvid"] == "BV1xx411c7mD"
    assert body["results"][0]["play"] == 1000
    assert body["results"][0]["danmaku"] == 20
    assert body["results"][0]["pic"] == "//i0.hdslb.com/demo.jpg"


def test_bilibili_user_keyword_is_trimmed_before_search(client, monkeypatch):
    captured: dict[str, str] = {}

    class FakeBilibiliClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def search_users(self, keyword, page=1, max_results=20):
            captured["keyword"] = keyword
            return [BilibiliSearchUserItem(mid=1, uname="tester")]

    _patch_bilibili_client(monkeypatch, FakeBilibiliClient)

    resp = client.get("/api/v1/bilibili/search/users", params={"keyword": "  tester  "})

    assert resp.status_code == 200
    assert captured["keyword"] == "tester"
    body = resp.json()
    assert body["keyword"] == "tester"
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["results"][0]["uname"] == "tester"


def test_bilibili_article_keyword_is_trimmed_before_search(client, monkeypatch):
    captured: dict[str, str] = {}

    class FakeBilibiliClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def search_articles(self, keyword, page=1, max_results=20):
            captured["keyword"] = keyword
            return [BilibiliArticleResult(id=1, title="article")]

    _patch_bilibili_client(monkeypatch, FakeBilibiliClient)

    resp = client.get("/api/v1/bilibili/search/articles", params={"keyword": "  article  "})

    assert resp.status_code == 200
    assert captured["keyword"] == "article"
    body = resp.json()
    assert body["keyword"] == "article"
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["results"][0]["title"] == "article"
    assert body["results"][0]["description"] == body["results"][0]["desc"]


def test_bilibili_bvid_is_trimmed_before_detail_lookup(client, monkeypatch):
    captured: dict[str, str] = {}

    class FakeBilibiliClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get_video_details(self, bvid):
            captured["bvid"] = bvid
            return BilibiliVideoDetail(bvid=bvid, title="video")

    _patch_bilibili_client(monkeypatch, FakeBilibiliClient)

    resp = client.get("/api/v1/bilibili/video/%20BV1xx411c7mD%20")

    assert resp.status_code == 200
    assert captured["bvid"] == "BV1xx411c7mD"
    body = resp.json()
    assert body["bvid"] == "BV1xx411c7mD"
    assert body["data"]["bvid"] == "BV1xx411c7mD"
    assert body["data"]["title"] == "video"


@pytest.mark.parametrize(
    ("exc_cls", "code", "expected_status"),
    [
        (BilibiliNotFound, 62002, 404),
        (BilibiliAuthRequired, -101, 401),
        (BilibiliRateLimited, -412, 429),
        (BilibiliRiskControl, -352, 403),
        (BilibiliError, -500, 502),
    ],
)
def test_bilibili_error_detail_redacts_secrets(
    client,
    monkeypatch,
    exc_cls,
    code,
    expected_status,
):
    secret_message = (
        "upstream failed Cookie: SESSDATA=sess-secret; sid=session-secret "
        "token=api-secret callback https://bili.example/cb?apiKey=url-secret&safe=1"
    )

    class FakeBilibiliClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get_video_details(self, bvid):
            raise exc_cls(code, secret_message)

    _patch_bilibili_client(monkeypatch, FakeBilibiliClient)

    resp = client.get("/api/v1/bilibili/video/BV1xx411c7mD")

    assert resp.status_code == expected_status
    detail = resp.json()["detail"]
    assert "sess-secret" not in detail
    assert "session-secret" not in detail
    assert "api-secret" not in detail
    assert "url-secret" not in detail
    assert "Cookie:***" in detail
    assert "token:***" in detail
    assert "apiKey=***" in detail
    assert "safe=1" in detail
