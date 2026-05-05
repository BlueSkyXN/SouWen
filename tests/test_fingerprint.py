"""SouWen 浏览器指纹模块测试。

覆盖 ``souwen.core.fingerprint`` 中浏览器 User-Agent 生成、HTTP 头构造、curl_cffi impersonate 参数等。
验证随机/默认指纹的有效性、headers 完整性、api_key/bearer_token/email 头注入、以及指纹轮换。

测试清单：
- ``TestBrowserFingerprint``：随机/默认指纹生成、headers 字段完整性、impersonate 参数
- ``TestGetApiHeaders``：版本号、email From 头、bearer_token Authorization 头、api_key 头注入
"""

from souwen.core.fingerprint import (
    BrowserFingerprint,
    get_api_headers,
    get_default_fingerprint,
    get_random_fingerprint,
)
from souwen import __version__


class TestBrowserFingerprint:
    """BrowserFingerprint 测试"""

    def test_random_returns_fingerprint(self):
        """get_random_fingerprint 返回 BrowserFingerprint"""
        fp = get_random_fingerprint()
        assert isinstance(fp, BrowserFingerprint)

    def test_default_returns_first_version(self):
        """get_default_fingerprint 返回第一个版本"""
        fp = get_default_fingerprint()
        assert fp.user_agent.startswith("Mozilla/5.0")
        assert "Chrome/146" in fp.user_agent

    def test_headers_has_required_keys(self):
        """headers 包含必要的 key"""
        fp = get_default_fingerprint()
        headers = fp.headers
        required = {
            "User-Agent",
            "sec-ch-ua",
            "sec-ch-ua-mobile",
            "sec-ch-ua-platform",
            "Accept",
            "Accept-Language",
            "Accept-Encoding",
        }
        assert required.issubset(headers.keys())

    def test_headers_user_agent_matches(self):
        """headers 中的 UA 与属性一致"""
        fp = get_default_fingerprint()
        assert fp.headers["User-Agent"] == fp.user_agent

    def test_impersonate_property(self):
        """impersonate 返回 curl_cffi 参数"""
        fp = get_default_fingerprint()
        assert fp.impersonate.startswith("chrome") or fp.impersonate.startswith("safari")

    def test_rotate_returns_new_instance(self):
        """rotate 返回新的 BrowserFingerprint"""
        fp = get_default_fingerprint()
        rotated = fp.rotate()
        assert isinstance(rotated, BrowserFingerprint)
        assert rotated is not fp

    def test_headers_sec_fetch_keys(self):
        """headers 包含 Sec-Fetch 系列"""
        fp = get_default_fingerprint()
        headers = fp.headers
        assert "Sec-Fetch-Dest" in headers
        assert "Sec-Fetch-Mode" in headers
        assert "Sec-Fetch-Site" in headers
        assert "Sec-Fetch-User" in headers


class TestGetApiHeaders:
    """get_api_headers 测试"""

    def test_includes_version_in_ua(self):
        """User-Agent 包含版本号"""
        headers = get_api_headers()
        assert __version__ in headers["User-Agent"]
        assert "SouWen" in headers["User-Agent"]

    def test_email_adds_from(self):
        """email 参数添加 From 头"""
        headers = get_api_headers(email="test@example.com")
        assert headers["From"] == "test@example.com"

    def test_no_email_no_from(self):
        """无 email 时没有 From 头"""
        headers = get_api_headers()
        assert "From" not in headers

    def test_bearer_token_adds_authorization(self):
        """bearer_token 参数添加 Authorization 头"""
        headers = get_api_headers(bearer_token="tok_abc123")
        assert headers["Authorization"] == "Bearer tok_abc123"

    def test_api_key_adds_header(self):
        """api_key 参数添加 X-API-Key 头"""
        headers = get_api_headers(api_key="key_xyz")
        assert headers["X-API-Key"] == "key_xyz"

    def test_no_token_no_auth(self):
        """无 token 时没有 Authorization"""
        headers = get_api_headers()
        assert "Authorization" not in headers

    def test_all_params_together(self):
        """所有参数组合使用"""
        headers = get_api_headers(
            email="a@b.com",
            api_key="k1",
            bearer_token="t1",
        )
        assert "From" in headers
        assert "X-API-Key" in headers
        assert "Authorization" in headers
