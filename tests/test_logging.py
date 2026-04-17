"""日志脱敏过滤器测试（P1-1）。

覆盖 ``souwen.logging_config`` 中 ``_scrub`` 与 ``SensitiveDataFilter``
的脱敏行为，保证日志里不会泄漏 Bearer Token、API Key、密码等敏感字段。

测试分组：
- ``TestScrub``：纯函数 ``_scrub`` 的各种匹配模式（Bearer / api_key 查询串
  / password=... / 大小写 / 空输入等）。
- ``TestSensitiveDataFilter``：``logging.Filter`` 实现会把记录的 ``msg``
  及 ``args`` 一并脱敏，且对非字符串 ``msg`` 永远不抛异常。
"""

from __future__ import annotations

import logging

from souwen.logging_config import SensitiveDataFilter, _scrub


def _make_record(msg: str, args: tuple = ()) -> logging.LogRecord:
    """辅助函数：构造一条 ``logging.LogRecord`` 供过滤器测试使用。"""
    return logging.LogRecord(
        name="t", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=None,
    )


class TestScrub:
    def test_bearer_token_masked(self):
        """``Authorization: Bearer <token>`` 中的 token 必须被替换为 ``***``。"""
        out = _scrub("Authorization: Bearer abcdefg12345")
        assert "abcdefg12345" not in out
        assert "***" in out

    def test_bare_bearer_masked(self):
        """不带 ``Authorization:`` 前缀的裸 ``Bearer xxx`` 同样要被脱敏。"""
        out = _scrub("got Bearer xyz789longtoken here")
        assert "xyz789longtoken" not in out
        assert "Bearer ***" in out

    def test_api_key_query(self):
        """URL query 中的 ``api_key=...`` 必须被脱敏，不影响其它参数。"""
        out = _scrub("GET /search?api_key=SECRETLONGVALUE12345&q=hello")
        assert "SECRETLONGVALUE" not in out
        assert "***" in out

    def test_kv_password(self):
        """``password=...`` 的键值对（无论长度）都要被脱敏。"""
        out = _scrub("password=short")
        assert "short" not in out
        assert "***" in out

    def test_non_sensitive_unchanged(self):
        """不含敏感字段的字符串必须原样返回，避免误伤。"""
        assert _scrub("count=42 name=alice") == "count=42 name=alice"

    def test_case_insensitive(self):
        """字段名大小写不敏感（``API_KEY`` / ``api_key`` 都应命中）。"""
        out = _scrub('API_KEY: "MYLONGSECRETVALUE12345"')
        assert "MYLONGSECRETVALUE" not in out
        assert "***" in out

    def test_none_or_empty(self):
        """空字符串照原样返回；非字符串（None）不应崩溃而是原样返回。"""
        assert _scrub("") == ""
        # 非字符串原样返回
        assert _scrub(None) is None  # type: ignore[arg-type]


class TestSensitiveDataFilter:
    def test_filter_rewrites_msg(self):
        """过滤器必须就地改写 ``record.msg``，让 ``getMessage()`` 输出脱敏结果。"""
        f = SensitiveDataFilter()
        rec = _make_record("auth header: Authorization: Bearer xyz123456longtoken")
        assert f.filter(rec) is True
        assert "xyz123456longtoken" not in rec.getMessage()
        assert "***" in rec.getMessage()

    def test_filter_with_tuple_args(self):
        """当日志使用 ``%s`` + args 格式化时，args 中的敏感值也必须脱敏。"""
        f = SensitiveDataFilter()
        rec = _make_record("request %s", ("api_key=SECRETLONGVALUE12345",))
        assert f.filter(rec) is True
        msg = rec.getMessage()
        assert "SECRETLONGVALUE" not in msg
        assert "***" in msg

    def test_filter_scrubs_msg_with_secret_inline(self):
        """内联在 msg 模板里的 ``token=...`` 也要被清除。"""
        f = SensitiveDataFilter()
        rec = _make_record("token=SECRETVALUELONG in request")
        assert f.filter(rec) is True
        assert "SECRETVALUELONG" not in rec.getMessage()

    def test_filter_never_raises(self):
        """非字符串 msg（数字等）通过过滤器不抛异常——日志路径必须绝对健壮。"""
        # 确保非字符串 msg 也安全通过
        f = SensitiveDataFilter()
        rec = _make_record("plain log with no secrets")
        rec.msg = 12345  # type: ignore[assignment]
        assert f.filter(rec) is True
