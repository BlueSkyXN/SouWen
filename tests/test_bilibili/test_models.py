"""Bilibili Pydantic 模型单元测试（精简版：搜索 + 抓取）"""

from __future__ import annotations

from souwen.web.bilibili.models import (
    BilibiliArticleResult,
    BilibiliSearchUserItem,
    BilibiliVideoDetail,
    VideoOwner,
    VideoStat,
)


def test_video_detail_defaults():
    v = BilibiliVideoDetail()
    assert v.bvid == ""
    assert v.aid == 0
    assert v.title == ""
    assert v.duration == 0
    assert isinstance(v.owner, VideoOwner)
    assert isinstance(v.stat, VideoStat)
    assert v.tags == []


def test_video_detail_url_property():
    v = BilibiliVideoDetail(bvid="BV1xx411c7mD")
    assert v.url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert BilibiliVideoDetail().url == ""


def test_video_detail_duration_str():
    assert BilibiliVideoDetail(duration=0).duration_str == "0:00"
    assert BilibiliVideoDetail(duration=5).duration_str == "0:05"
    assert BilibiliVideoDetail(duration=65).duration_str == "1:05"
    assert BilibiliVideoDetail(duration=3661).duration_str == "61:01"


def test_search_user_item_space_url():
    u = BilibiliSearchUserItem(mid=12345, uname="X")
    assert u.space_url == "https://space.bilibili.com/12345"
    assert BilibiliSearchUserItem().space_url == ""


def test_article_result_defaults():
    a = BilibiliArticleResult()
    assert a.id == 0
    assert a.title == ""
    assert a.image_urls == []


def test_article_result_from_dict():
    raw = {
        "id": 999,
        "title": "示例文章",
        "author": "作者",
        "mid": 100,
        "category_name": "科技",
        "desc": "摘要",
        "view": 1234,
        "like": 56,
        "reply": 7,
        "pub_date": 1700000000,
        "url": "https://www.bilibili.com/read/cv999",
        "image_urls": ["https://x/a.jpg"],
    }
    a = BilibiliArticleResult(**raw)
    assert a.id == 999
    assert a.title == "示例文章"
    assert a.view == 1234
    assert a.image_urls == ["https://x/a.jpg"]


def test_models_extra_allow():
    """extra="allow" — 未知字段不应抛验证错误"""
    v = BilibiliVideoDetail(bvid="BV1", title="t", new_field_2099="future-proof")
    assert v.bvid == "BV1"
    assert v.model_extra == {"new_field_2099": "future-proof"}

    u = BilibiliSearchUserItem(mid=1, brand_new="x")
    assert u.model_extra == {"brand_new": "x"}

    a = BilibiliArticleResult(id=1, foo="bar")
    assert a.model_extra == {"foo": "bar"}
