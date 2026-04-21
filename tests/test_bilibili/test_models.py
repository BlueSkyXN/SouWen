"""Bilibili Pydantic 模型单元测试"""

from __future__ import annotations

from souwen.web.bilibili.models import (
    BilibiliComment,
    BilibiliPopularVideo,
    BilibiliRankVideo,
    BilibiliSubtitle,
    BilibiliSubtitleLine,
    BilibiliUserInfo,
    BilibiliVideoDetail,
    CommentContent,
    CommentMember,
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


def test_user_info_space_url():
    u = BilibiliUserInfo(mid=12345)
    assert u.space_url == "https://space.bilibili.com/12345"
    assert BilibiliUserInfo().space_url == ""


def test_comment_text_property():
    c = BilibiliComment(rpid=1, content=CommentContent(message="你好世界"))
    assert c.text == "你好世界"
    assert BilibiliComment().text == ""


def test_subtitle_full_text():
    sub = BilibiliSubtitle(
        lan="zh-CN",
        lan_doc="中文",
        lines=[
            BilibiliSubtitleLine(**{"from": 0.0, "to": 1.0, "content": "line1"}),
            BilibiliSubtitleLine(**{"from": 1.0, "to": 2.0, "content": "line2"}),
            BilibiliSubtitleLine(**{"from": 2.0, "to": 3.0, "content": ""}),
            BilibiliSubtitleLine(**{"from": 3.0, "to": 4.0, "content": "line3"}),
        ],
    )
    assert sub.full_text == "line1\nline2\nline3"
    assert BilibiliSubtitle().full_text == ""


def test_popular_video_from_dict():
    """模拟 /x/web-interface/popular 真实响应字段"""
    raw = {
        "bvid": "BV1AB4y1z7Cd",
        "aid": 1234567890,
        "title": "热门视频示例",
        "pic": "https://i0.hdslb.com/bfs/archive/x.jpg",
        "desc": "视频简介",
        "duration": 300,
        "pubdate": 1700000000,
        "owner": {"mid": 100, "name": "UP主", "face": "https://x/avatar.jpg"},
        "stat": {"view": 9999, "danmaku": 100, "like": 500},
        "rcmd_reason": "",
    }
    v = BilibiliPopularVideo(**raw)
    assert v.bvid == "BV1AB4y1z7Cd"
    assert v.title == "热门视频示例"
    assert v.description == "视频简介"
    assert v.owner.mid == 100
    assert v.owner.name == "UP主"
    assert v.stat.view == 9999
    assert v.stat.like == 500
    assert v.url == "https://www.bilibili.com/video/BV1AB4y1z7Cd"


def test_rank_video_with_score():
    raw = {
        "bvid": "BV1xx",
        "aid": 1,
        "title": "排行榜视频",
        "pic": "https://x/p.jpg",
        "desc": "描述",
        "duration": 120,
        "pubdate": 1700000000,
        "owner": {"mid": 1, "name": "U"},
        "stat": {"view": 1000},
        "rank_index": 3,
        "score": 88888,
    }
    v = BilibiliRankVideo(**raw)
    assert v.rank_index == 3
    assert v.score == 88888
    assert v.description == "描述"
    assert v.url == "https://www.bilibili.com/video/BV1xx"


def test_models_extra_allow():
    """extra="allow" — 未知字段不应抛验证错误"""
    v = BilibiliVideoDetail(bvid="BV1", title="t", new_field_2099="future-proof")
    assert v.bvid == "BV1"
    assert v.model_extra == {"new_field_2099": "future-proof"}

    u = BilibiliUserInfo(mid=1, brand_new_field=[1, 2, 3])
    assert u.model_extra == {"brand_new_field": [1, 2, 3]}

    c = CommentMember(mid=1, foo="bar")
    assert c.model_extra == {"foo": "bar"}
