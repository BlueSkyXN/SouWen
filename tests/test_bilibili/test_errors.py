"""Bilibili 错误码到异常类映射测试"""

from __future__ import annotations

import pytest

from souwen.web.bilibili._errors import (
    BilibiliAuthRequired,
    BilibiliError,
    BilibiliNotFound,
    BilibiliRateLimited,
    BilibiliRiskControl,
    raise_for_code,
)


def test_raise_for_code_not_found():
    with pytest.raises(BilibiliNotFound) as exc:
        raise_for_code(-404, "not found")
    assert exc.value.code == -404
    assert exc.value.message == "not found"

    with pytest.raises(BilibiliNotFound):
        raise_for_code(62002, "稿件不可见")
    with pytest.raises(BilibiliNotFound):
        raise_for_code(62004, "稿件审核中")


def test_raise_for_code_auth_required():
    with pytest.raises(BilibiliAuthRequired) as exc:
        raise_for_code(-101, "账号未登录")
    assert exc.value.code == -101


def test_raise_for_code_rate_limited():
    with pytest.raises(BilibiliRateLimited):
        raise_for_code(-412, "请求过快")
    with pytest.raises(BilibiliRateLimited):
        raise_for_code(412, "rate limit")


def test_raise_for_code_risk_control():
    with pytest.raises(BilibiliRiskControl) as exc:
        raise_for_code(-352, "风控校验失败")
    assert exc.value.code == -352


def test_raise_for_code_unknown():
    """未映射的错误码兜底为 BilibiliError 基类"""
    with pytest.raises(BilibiliError) as exc:
        raise_for_code(-9999, "unknown")
    assert type(exc.value) is BilibiliError
    assert exc.value.code == -9999


def test_error_inheritance():
    for cls in (
        BilibiliNotFound,
        BilibiliAuthRequired,
        BilibiliRateLimited,
        BilibiliRiskControl,
    ):
        assert issubclass(cls, BilibiliError)
        assert issubclass(cls, Exception)


def test_error_str_contains_code_and_message():
    e = BilibiliError(-1, "boom")
    s = str(e)
    assert "-1" in s and "boom" in s
