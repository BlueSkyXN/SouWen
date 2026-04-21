"""Bilibili WBI 签名模块单元测试

覆盖：
    - 置换表长度
    - mixin_key 计算（含已知向量）
    - URL key 提取
    - 完整签名（已知输入 → 已知 w_rid）
    - 特殊字符 !'()* 过滤
    - 参数按 key 字典序排序
    - WbiSigner 缓存命中 / TTL / 失效
"""

from __future__ import annotations

import hashlib
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from souwen.web.bilibili.wbi import (
    MIXIN_KEY_ENC_TAB,
    WbiSigner,
    _extract_key_from_url,
    get_mixin_key,
    sign_params,
)


# 已知测试向量（来自 bilibili-API-collect 文档示例）
_IMG_KEY = "7cd084941338484aae1ad9425b84077c"
_SUB_KEY = "4932caff0ff746eab6f01bf08b70ac45"


def test_mixin_key_enc_tab_length():
    """置换表必须恰好 64 项"""
    assert len(MIXIN_KEY_ENC_TAB) == 64
    assert all(0 <= i < 64 for i in MIXIN_KEY_ENC_TAB)


def test_get_mixin_key():
    """已知 img/sub_key → 已知 mixin_key"""
    mixin = get_mixin_key(_IMG_KEY, _SUB_KEY)
    assert len(mixin) == 32
    expected = "ea1db124af3c7062474693fa704f4ff8"
    assert mixin == expected


def test_get_mixin_key_truncates_to_32():
    long_img = "x" * 64
    long_sub = "y" * 64
    assert len(get_mixin_key(long_img, long_sub)) == 32


def test_extract_key_from_url():
    url = "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png"
    assert _extract_key_from_url(url) == "7cd084941338484aae1ad9425b84077c"


def test_extract_key_from_url_no_extension():
    url = "https://i0.hdslb.com/bfs/wbi/abc123"
    assert _extract_key_from_url(url) == "abc123"


def test_sign_params():
    """完整签名：固定 ts、固定 keys → 固定 w_rid"""
    params = {"foo": "bar", "baz": 1}
    ts = 1700000000
    out = sign_params(params, _IMG_KEY, _SUB_KEY, ts=ts)

    assert out["wts"] == str(ts)
    assert "w_rid" in out
    assert len(out["w_rid"]) == 32
    assert out["foo"] == "bar"
    assert out["baz"] == "1"

    mixin = get_mixin_key(_IMG_KEY, _SUB_KEY)
    expected_query = f"baz=1&foo=bar&wts={ts}"
    expected_w_rid = hashlib.md5((expected_query + mixin).encode("utf-8")).hexdigest()
    assert out["w_rid"] == expected_w_rid


def test_sign_params_filters_special_chars():
    """!'()* 字符在签名计算中被剥离"""
    params = {"q": "ba!'(*)r"}
    ts = 1700000000
    out = sign_params(params, _IMG_KEY, _SUB_KEY, ts=ts)

    mixin = get_mixin_key(_IMG_KEY, _SUB_KEY)
    expected_query = f"q=bar&wts={ts}"
    expected_w_rid = hashlib.md5((expected_query + mixin).encode("utf-8")).hexdigest()
    assert out["w_rid"] == expected_w_rid


def test_sign_params_sorts_keys():
    """参数按 key 字典序参与签名（与插入顺序无关）"""
    ts = 1700000000
    a = sign_params({"b": "1", "a": "2", "c": "3"}, _IMG_KEY, _SUB_KEY, ts=ts)
    b = sign_params({"c": "3", "a": "2", "b": "1"}, _IMG_KEY, _SUB_KEY, ts=ts)
    assert a["w_rid"] == b["w_rid"]

    mixin = get_mixin_key(_IMG_KEY, _SUB_KEY)
    expected_query = f"a=2&b=1&c=3&wts={ts}"
    expected_w_rid = hashlib.md5((expected_query + mixin).encode("utf-8")).hexdigest()
    assert a["w_rid"] == expected_w_rid


def _make_nav_resp():
    fake_resp = MagicMock()
    fake_resp.json = MagicMock(
        return_value={
            "code": 0,
            "data": {
                "wbi_img": {
                    "img_url": f"https://i0.hdslb.com/bfs/wbi/{_IMG_KEY}.png",
                    "sub_url": f"https://i0.hdslb.com/bfs/wbi/{_SUB_KEY}.png",
                }
            },
        }
    )
    return fake_resp


async def test_wbi_signer_cache():
    """连续两次 sign 应只触发一次 nav 抓取（cache 命中）"""
    signer = WbiSigner(cache_ttl=3600)
    fetch_fn = AsyncMock(return_value=_make_nav_resp())

    out1 = await signer.sign(fetch_fn, {"mid": "1"}, ts=1700000000)
    out2 = await signer.sign(fetch_fn, {"mid": "2"}, ts=1700000000)

    assert fetch_fn.await_count == 1
    assert out1["w_rid"] and out2["w_rid"]
    assert signer.has_valid_cache is True


async def test_wbi_signer_cache_ttl_expiry(monkeypatch):
    """超出 TTL 后再次 sign 应重新抓取 nav"""
    signer = WbiSigner(cache_ttl=10)
    fetch_fn = AsyncMock(return_value=_make_nav_resp())

    await signer.sign(fetch_fn, {"k": "1"})
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 100)
    await signer.sign(fetch_fn, {"k": "2"})
    assert fetch_fn.await_count == 2


async def test_wbi_signer_invalidate():
    """invalidate() 应清空缓存，下次 sign 重新抓取"""
    signer = WbiSigner()
    fetch_fn = AsyncMock(return_value=_make_nav_resp())

    await signer.sign(fetch_fn, {"k": "1"})
    assert signer.has_valid_cache is True
    signer.invalidate()
    assert signer.has_valid_cache is False
    await signer.sign(fetch_fn, {"k": "2"})
    assert fetch_fn.await_count == 2


async def test_wbi_signer_missing_keys_raises():
    """nav 响应缺少 wbi_img 时抛 ValueError"""
    signer = WbiSigner()
    fake_resp = MagicMock()
    fake_resp.json = MagicMock(return_value={"code": -101, "data": {}})
    fetch_fn = AsyncMock(return_value=fake_resp)
    with pytest.raises(ValueError):
        await signer.sign(fetch_fn, {"k": "v"})
