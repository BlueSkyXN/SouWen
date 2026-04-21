"""Bilibili 搜索客户端单元测试

文件用途：
    覆盖 souwen.web.bilibili.BilibiliClient 的核心行为：
    - 正常搜索：返回结果数量、字段映射正确
    - HTML 高亮标签清理：title 中的 <em class="keyword"> 被去除
    - 空结果处理：data.result 为空时安全返回
    - description 截断：超长 snippet 被裁剪到 300 字符
    - API 错误码处理：code != 0 时降级为空结果
    - HTTP 异常处理：_fetch 抛出异常时降级为空结果
    - 排序参数透传：order 参数被拼接到 URL
    - _clean_html 静态方法的边界值

Mock 策略：
    BaseScraper._fetch 返回一个具有 .json() 方法的伪响应对象，
    避免真实 HTTP 调用；同时构造 BilibiliClient 时 stub 掉父类
    __init__，跳过 curl_cffi/httpx 客户端的实际创建。
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from souwen.web.bilibili import BilibiliClient
from souwen.models import SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    """伪 HTTP 响应：仅暴露 BilibiliClient 用到的接口"""

    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return self._payload


def _build_client() -> BilibiliClient:
    """构造一个跳过网络初始化的 BilibiliClient"""
    client = BilibiliClient.__new__(BilibiliClient)
    # 复刻 BaseScraper 中 _fetch / search 会读取的属性
    client.min_delay = 0.0
    client.max_delay = 0.0
    client.max_retries = 1
    client._backoff_multiplier = 1.0
    client._fingerprint = None
    client._channel_headers = {}
    client._use_curl_cffi = False
    client._curl_session = None
    client._httpx_client = None
    client._resolved_base_url = BilibiliClient.BASE_URL
    # WBI 密钥缓存（None 表示未缓存）
    client._wbi_cache = None
    # WBI 密钥刷新锁（None 表示懒加载，首次调用时创建）
    client._wbi_lock = None
    return client


def _sample_payload(items: list[dict] | None = None, num_results: int = 100) -> dict:
    return {
        "code": 0,
        "message": "0",
        "data": {
            "result": items if items is not None else [],
            "numResults": num_results,
            "numPages": 5,
        },
    }


def _sample_item(**overrides) -> dict:
    base = {
        "title": '<em class="keyword">Python</em> 入门教程',
        "arcurl": "https://www.bilibili.com/video/BV1xx411c7mD",
        "description": "这是一个 Python 入门教程视频",
        "author": "UP主A",
        "mid": 12345678,
        "play": 99999,
        "video_review": 100,
        "favorites": 50,
        "duration": "12:34",
        "pubdate": 1609459200,
        "tag": "python,教程,编程",
        "bvid": "BV1xx411c7mD",
        "aid": 999,
    }
    base.update(overrides)
    return base


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---------------------------------------------------------------------------
# 枚举扩展
# ---------------------------------------------------------------------------


def test_bilibili_source_type_exists():
    """SourceType.WEB_BILIBILI 枚举值应已注册"""
    assert SourceType.WEB_BILIBILI.value == "web_bilibili"


# ---------------------------------------------------------------------------
# _clean_html
# ---------------------------------------------------------------------------


def test_clean_html_strips_em_tags():
    text = '<em class="keyword">Python</em> 教程'
    assert BilibiliClient._clean_html(text) == "Python 教程"


def test_clean_html_strips_multiple_tags():
    text = "<b>hello</b> <i>world</i>"
    assert BilibiliClient._clean_html(text) == "hello world"


def test_clean_html_handles_empty():
    assert BilibiliClient._clean_html("") == ""
    assert BilibiliClient._clean_html(None) == ""  # type: ignore[arg-type]


def test_clean_html_strips_whitespace():
    assert BilibiliClient._clean_html("  <em>x</em>  ") == "x"


# ---------------------------------------------------------------------------
# search() — 正常路径
# ---------------------------------------------------------------------------


def test_search_returns_results():
    client = _build_client()
    payload = _sample_payload(
        items=[_sample_item(), _sample_item(arcurl="https://www.bilibili.com/video/BV2")]
    )
    fake_resp = _FakeResponse(payload)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)) as mocked:
        resp = _run(client.search("python", max_results=10))

    assert mocked.await_count == 1
    # 校验 URL 与必备 headers
    call_args = mocked.await_args
    assert "search_type=video" in call_args.args[0]
    assert "keyword=python" in call_args.args[0]
    assert "order=totalrank" in call_args.args[0]
    assert call_args.kwargs["headers"]["Referer"] == "https://www.bilibili.com"

    assert resp.query == "python"
    assert resp.source == SourceType.WEB_BILIBILI
    assert len(resp.results) == 2
    assert resp.total_results == 100

    first = resp.results[0]
    assert first.title == "Python 入门教程"  # <em> 被清理
    assert first.url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert first.snippet == "这是一个 Python 入门教程视频"
    assert first.engine == "bilibili"
    assert first.raw["author"] == "UP主A"
    assert first.raw["play"] == 99999
    assert first.raw["bvid"] == "BV1xx411c7mD"


def test_search_html_tag_cleaning_in_results():
    client = _build_client()
    payload = _sample_payload(
        items=[_sample_item(title='<em class="keyword">AI</em> <b>大模型</b>')]
    )
    fake_resp = _FakeResponse(payload)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("ai"))

    assert resp.results[0].title == "AI 大模型"


def test_search_empty_results():
    client = _build_client()
    fake_resp = _FakeResponse(_sample_payload(items=[], num_results=0))

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("nonexistent"))

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_BILIBILI


def test_search_truncates_description():
    client = _build_client()
    long_desc = "a" * 1000
    payload = _sample_payload(items=[_sample_item(description=long_desc)])
    fake_resp = _FakeResponse(payload)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert len(resp.results[0].snippet) == 300
    assert resp.results[0].snippet == "a" * 300


def test_search_respects_max_results():
    client = _build_client()
    items = [_sample_item(arcurl=f"https://www.bilibili.com/video/BV{i}") for i in range(10)]
    fake_resp = _FakeResponse(_sample_payload(items=items))

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x", max_results=3))

    assert len(resp.results) == 3


def test_search_skips_items_missing_title_or_url():
    client = _build_client()
    items = [
        _sample_item(),
        _sample_item(title="", arcurl="https://www.bilibili.com/video/BVno-title"),
        _sample_item(title="ok", arcurl=""),
        {"not": "a-dict"},  # 非 dict 应被跳过
    ]
    # items 列表里包含一个非 dict 元素
    raw_items: list = list(items)
    raw_items.append("string-not-dict")  # type: ignore[arg-type]
    fake_resp = _FakeResponse(_sample_payload(items=raw_items))

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    # 只有第一个 _sample_item() 是合法完整的
    assert len(resp.results) == 1
    assert resp.results[0].title == "Python 入门教程"


# ---------------------------------------------------------------------------
# search() — 异常 / 降级路径
# ---------------------------------------------------------------------------


def test_search_handles_api_error_code():
    client = _build_client()
    fake_resp = _FakeResponse({"code": -412, "message": "请求被拦截", "data": None})

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0


def test_search_handles_fetch_exception():
    client = _build_client()

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(side_effect=RuntimeError("boom"))):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_BILIBILI


def test_search_handles_invalid_json():
    client = _build_client()

    class _BadResp:
        status_code = 200
        text = "not json"
        headers: dict = {}

        def json(self):
            raise ValueError("invalid json")

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_BadResp())):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0


def test_search_handles_non_list_result_field():
    """/search/all/v2 端点的 data.result 是分组数组（dict 列表），但若返回非列表也要兜底"""
    client = _build_client()
    payload = {"code": 0, "data": {"result": {"unexpected": "shape"}, "numResults": 0}}
    fake_resp = _FakeResponse(payload)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert resp.results == []


# ---------------------------------------------------------------------------
# search() — 排序参数
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("order", ["totalrank", "click", "pubdate", "dm", "stow"])
def test_search_passes_order_param(order):
    client = _build_client()
    fake_resp = _FakeResponse(_sample_payload(items=[]))

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)) as mocked:
        _run(client.search("x", order=order))

    assert f"order={order}" in mocked.await_args.args[0]


def test_search_clamps_max_results_to_50():
    client = _build_client()
    fake_resp = _FakeResponse(_sample_payload(items=[]))

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)) as mocked:
        _run(client.search("x", max_results=999))

    assert "page_size=50" in mocked.await_args.args[0]


# ---------------------------------------------------------------------------
# WBI 签名算法单元测试（纯函数，不依赖网络）
# ---------------------------------------------------------------------------


def test_get_mixin_key_length():
    """_get_mixin_key 返回 32 字符的混合密钥"""
    from souwen.web.bilibili import _get_mixin_key

    img = "a" * 32
    sub = "b" * 32
    result = _get_mixin_key(img, sub)
    assert len(result) == 32


def test_get_mixin_key_uses_encoding_table():
    """_get_mixin_key 按编码表重排字符（验证前几个字符）"""
    from souwen.web.bilibili import _get_mixin_key, _MIXIN_KEY_ENC_TAB

    # 构造字母表方便验证
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789AB"
    result = _get_mixin_key(alphabet[:32], alphabet[32:])
    # 验证第一个字符：_MIXIN_KEY_ENC_TAB[0] = 46 → alphabet[46]
    orig = alphabet
    expected_first = orig[_MIXIN_KEY_ENC_TAB[0]]
    assert result[0] == expected_first


def test_sign_wbi_params_contains_w_rid_and_wts():
    """_sign_wbi_params 返回包含 w_rid 和 wts 的查询字符串"""
    from souwen.web.bilibili import _sign_wbi_params

    img_key = "7cd084941338484aae1ad9425b84077c"
    sub_key = "4932caff0ff746eab6f01bf08b70ac45"
    params = {"mid": 2, "photo": "1"}
    result = _sign_wbi_params(params, img_key, sub_key)

    assert "w_rid=" in result
    assert "wts=" in result
    # w_rid 是 32 字符 MD5 hex
    import re as _re
    m = _re.search(r"w_rid=([0-9a-f]{32})", result)
    assert m is not None


def test_sign_wbi_params_filters_special_chars():
    """_sign_wbi_params 过滤值中的特殊字符 !'()*"""
    from souwen.web.bilibili import _sign_wbi_params

    img_key = "7cd084941338484aae1ad9425b84077c"
    sub_key = "4932caff0ff746eab6f01bf08b70ac45"
    params = {"query": "hello!'()*world"}
    result = _sign_wbi_params(params, img_key, sub_key)

    # 特殊字符应被过滤掉
    assert "!" not in result.split("&")[0].split("=", 1)[1]


def test_sign_wbi_params_sorted_keys():
    """_sign_wbi_params 按 key 字母序排列参数（wts 除外）"""
    from souwen.web.bilibili import _sign_wbi_params

    img_key = "7cd084941338484aae1ad9425b84077c"
    sub_key = "4932caff0ff746eab6f01bf08b70ac45"
    params = {"z_param": "last", "a_param": "first", "mid": 123}
    result = _sign_wbi_params(params, img_key, sub_key)

    # 从查询字符串中提取参数名顺序（去掉 w_rid 的最后一项）
    keys = [kv.split("=")[0] for kv in result.split("&")]
    # a_param 应在 mid 和 z_param 之前，wts 和 w_rid 按排序也在正确位置
    assert keys.index("a_param") < keys.index("mid")
    assert keys.index("mid") < keys.index("z_param")


# ---------------------------------------------------------------------------
# WBI 密钥缓存测试
# ---------------------------------------------------------------------------


def _build_client_with_wbi_cache(cache_value: tuple | None = None) -> BilibiliClient:
    """构造带 WBI 缓存的 BilibiliClient"""
    client = _build_client()
    client._wbi_cache = cache_value
    return client


_NAV_RESPONSE = {
    "code": 0,
    "message": "0",
    "data": {
        "wbi_img": {
            "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
            "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
        }
    },
}


def test_get_wbi_keys_uses_cache():
    """有效缓存时不发起 HTTP 请求"""
    client = _build_client_with_wbi_cache(
        ("cached_img_key", "cached_sub_key", time.time())
    )

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock()) as mocked:
        img_key, sub_key = _run(client._get_wbi_keys())

    mocked.assert_not_awaited()
    assert img_key == "cached_img_key"
    assert sub_key == "cached_sub_key"


def test_get_wbi_keys_fetches_when_cache_expired():
    """缓存过期时发起 HTTP 请求更新密钥"""
    import time as _time

    expired_ts = _time.time() - 7200  # 2 小时前，已过期
    client = _build_client_with_wbi_cache(("old_img", "old_sub", expired_ts))
    fake_resp = _FakeResponse(_NAV_RESPONSE)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        img_key, sub_key = _run(client._get_wbi_keys())

    assert img_key == "7cd084941338484aae1ad9425b84077c"
    assert sub_key == "4932caff0ff746eab6f01bf08b70ac45"


def test_get_wbi_keys_fetches_when_no_cache():
    """无缓存时发起 HTTP 请求获取密钥"""
    client = _build_client_with_wbi_cache(None)
    fake_resp = _FakeResponse(_NAV_RESPONSE)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        img_key, sub_key = _run(client._get_wbi_keys())

    assert img_key == "7cd084941338484aae1ad9425b84077c"
    assert sub_key == "4932caff0ff746eab6f01bf08b70ac45"
    # 缓存应已更新
    assert client._wbi_cache is not None
    assert client._wbi_cache[0] == img_key


def test_get_wbi_keys_raises_on_bad_nav_response():
    """nav 端点返回格式错误时 _get_wbi_keys 抛出 RuntimeError"""
    client = _build_client_with_wbi_cache(None)
    bad_resp = _FakeResponse({"code": 0, "data": {}})  # 缺少 wbi_img

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=bad_resp)):
        with pytest.raises(RuntimeError):
            _run(client._get_wbi_keys())


# ---------------------------------------------------------------------------
# get_user_info()
# ---------------------------------------------------------------------------

_USER_INFO_RESPONSE = {
    "code": 0,
    "message": "0",
    "data": {
        "mid": 2,
        "name": "碧诗",
        "face": "https://i0.hdslb.com/bfs/face/face.jpg",
        "sign": "我是bilibili的第二个用户",
        "level": 6,
        "birthday": "1995-02-27",
        "tags": [],
        "official": None,
        "live_room": {
            "liveStatus": 0,
            "url": "https://live.bilibili.com/1",
        },
    },
}

_RELATION_STAT_RESPONSE = {
    "code": 0,
    "message": "0",
    "data": {
        "mid": 2,
        "follower": 5000000,
        "following": 300,
    },
}


def test_get_user_info_success():
    """get_user_info() 正确合并用户信息和关注粉丝数

    Mock 策略：_fetch 按顺序返回三个响应：
      1. nav 响应（_get_wbi_keys 用于获取 WBI 密钥）
      2. space/wbi/acc/info 响应（用户基本信息）
      3. relation/stat 响应（粉丝/关注数）
    """
    client = _build_client()
    nav_resp = _FakeResponse(_NAV_RESPONSE)
    user_resp = _FakeResponse(_USER_INFO_RESPONSE)
    stat_resp = _FakeResponse(_RELATION_STAT_RESPONSE)

    fetch_sequence = [nav_resp, user_resp, stat_resp]
    fetch_index = {"i": 0}

    async def fake_fetch(url, **kwargs):
        resp = fetch_sequence[fetch_index["i"]]
        fetch_index["i"] += 1
        return resp

    with patch.object(BilibiliClient, "_fetch", side_effect=fake_fetch):
        result = _run(client.get_user_info(2))

    assert result["mid"] == 2
    assert result["name"] == "碧诗"
    assert result["follower"] == 5000000
    assert result["following"] == 300


def test_get_user_info_stat_failure_graceful():
    """get_user_info() 在粉丝数请求失败时仍返回用户基本信息"""
    client = _build_client()
    nav_resp = _FakeResponse(_NAV_RESPONSE)
    user_resp = _FakeResponse(_USER_INFO_RESPONSE)

    call_count = {"n": 0}

    async def fake_fetch(url, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return nav_resp
        if call_count["n"] == 2:
            return user_resp
        raise RuntimeError("stat endpoint down")

    with patch.object(BilibiliClient, "_fetch", side_effect=fake_fetch):
        result = _run(client.get_user_info(2))

    assert result["name"] == "碧诗"
    assert result["follower"] is None
    assert result["following"] is None


# ---------------------------------------------------------------------------
# get_video_detail()
# ---------------------------------------------------------------------------

_VIDEO_DETAIL_RESPONSE = {
    "code": 0,
    "message": "0",
    "data": {
        "bvid": "BV1xx411c7mD",
        "aid": 170001,
        "title": "【教程】Python 入门",
        "desc": "这是一个教程",
        "pic": "https://example.com/cover.jpg",
        "owner": {"mid": 12345, "name": "UP主A", "face": "https://example.com/face.jpg"},
        "stat": {
            "view": 100000, "danmaku": 500, "reply": 200,
            "favorite": 1000, "coin": 300, "share": 50, "like": 5000,
        },
        "duration": 754,
        "pubdate": 1609459200,
        "ctime": 1609459100,
        "cid": 888,
        "tags": [],
    },
}


def test_get_video_detail_success():
    """get_video_detail() 正确返回视频详情"""
    client = _build_client()
    fake_resp = _FakeResponse(_VIDEO_DETAIL_RESPONSE)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        result = _run(client.get_video_detail("BV1xx411c7mD"))

    assert result["bvid"] == "BV1xx411c7mD"
    assert result["title"] == "【教程】Python 入门"
    assert result["stat"]["view"] == 100000


def test_get_video_detail_api_error_raises():
    """get_video_detail() 在 API 返回错误码时抛出 RuntimeError"""
    client = _build_client()
    fake_resp = _FakeResponse({"code": -400, "message": "请求错误", "data": None})

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(RuntimeError, match="code=-400"):
            _run(client.get_video_detail("BVinvalid"))


# ---------------------------------------------------------------------------
# get_related_videos()
# ---------------------------------------------------------------------------

_RELATED_RESPONSE = {
    "code": 0,
    "message": "0",
    "data": [
        {
            "bvid": "BV1aa411c7mA",
            "aid": 200001,
            "title": "相关视频 1",
            "pic": "https://example.com/1.jpg",
            "owner": {"mid": 99, "name": "UP主B"},
            "stat": {"view": 20000, "danmaku": 100},
            "duration": 360,
        },
        {
            "bvid": "BV1bb411c7mB",
            "aid": 200002,
            "title": "相关视频 2",
            "pic": "https://example.com/2.jpg",
            "owner": {"mid": 88, "name": "UP主C"},
            "stat": {"view": 15000, "danmaku": 50},
            "duration": 480,
        },
    ],
}


def test_get_related_videos_success():
    """get_related_videos() 正确返回相关视频列表"""
    client = _build_client()
    fake_resp = _FakeResponse(_RELATED_RESPONSE)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        result = _run(client.get_related_videos("BV1xx411c7mD"))

    assert len(result) == 2
    assert result[0]["bvid"] == "BV1aa411c7mA"
    assert result[1]["title"] == "相关视频 2"


def test_get_related_videos_empty():
    """get_related_videos() 在空列表时正确返回空列表"""
    client = _build_client()
    fake_resp = _FakeResponse({"code": 0, "message": "0", "data": []})

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        result = _run(client.get_related_videos("BV1xx411c7mD"))

    assert result == []
