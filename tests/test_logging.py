"""日志脱敏过滤器测试（P1-1）"""

from __future__ import annotations

import logging

from souwen.logging_config import SensitiveDataFilter, _scrub


def _make_record(msg: str, args: tuple = ()) -> logging.LogRecord:
    return logging.LogRecord(
        name="t", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=None,
    )


class TestScrub:
    def test_bearer_token_masked(self):
        out = _scrub("Authorization: Bearer abcdefg12345")
        assert "abcdefg12345" not in out
        assert "***" in out

    def test_bare_bearer_masked(self):
        out = _scrub("got Bearer xyz789longtoken here")
        assert "xyz789longtoken" not in out
        assert "Bearer ***" in out

    def test_api_key_query(self):
        out = _scrub("GET /search?api_key=SECRETLONGVALUE12345&q=hello")
        assert "SECRETLONGVALUE" not in out
        assert "***" in out

    def test_kv_password(self):
        out = _scrub("password=short")
        assert "short" not in out
        assert "***" in out

    def test_non_sensitive_unchanged(self):
        assert _scrub("count=42 name=alice") == "count=42 name=alice"

    def test_case_insensitive(self):
        out = _scrub('API_KEY: "MYLONGSECRETVALUE12345"')
        assert "MYLONGSECRETVALUE" not in out
        assert "***" in out

    def test_none_or_empty(self):
        assert _scrub("") == ""
        # 非字符串原样返回
        assert _scrub(None) is None  # type: ignore[arg-type]


class TestSensitiveDataFilter:
    def test_filter_rewrites_msg(self):
        f = SensitiveDataFilter()
        rec = _make_record("auth header: Authorization: Bearer xyz123456longtoken")
        assert f.filter(rec) is True
        assert "xyz123456longtoken" not in rec.getMessage()
        assert "***" in rec.getMessage()

    def test_filter_with_tuple_args(self):
        f = SensitiveDataFilter()
        rec = _make_record("request %s", ("api_key=SECRETLONGVALUE12345",))
        assert f.filter(rec) is True
        msg = rec.getMessage()
        assert "SECRETLONGVALUE" not in msg
        assert "***" in msg

    def test_filter_scrubs_msg_with_secret_inline(self):
        f = SensitiveDataFilter()
        rec = _make_record("token=SECRETVALUELONG in request")
        assert f.filter(rec) is True
        assert "SECRETVALUELONG" not in rec.getMessage()

    def test_filter_never_raises(self):
        # 确保非字符串 msg 也安全通过
        f = SensitiveDataFilter()
        rec = _make_record("plain log with no secrets")
        rec.msg = 12345  # type: ignore[assignment]
        assert f.filter(rec) is True
