"""内容抓取聚合模块单元测试

覆盖 ``souwen.web.fetch`` 中 SSRF 校验和 fetch_content 聚合逻辑。

测试清单：
- ``test_ssrf_rejects_private_ip``    ：拒绝私有 IP
- ``test_ssrf_rejects_non_http``      ：拒绝非 http/https 协议
- ``test_ssrf_rejects_no_hostname``   ：拒绝无主机名 URL
- ``test_ssrf_allows_public_https``   ：放行公网 HTTPS
- ``test_fetch_content_ssrf_block``   ：整合测试：SSRF 失败 URL 被过滤
- ``test_fetch_content_unknown_provider``：未知提供者返回错误
"""

from __future__ import annotations

import pytest

from souwen.web.fetch import validate_fetch_url, fetch_content


class TestSSRFValidation:
    """SSRF 校验单元测试"""

    def test_rejects_private_10(self):
        """拒绝 10.x.x.x 私有 IP"""
        ok, reason = validate_fetch_url("http://10.0.0.1/page")
        assert not ok
        assert "内部/私有" in reason or "DNS" in reason

    def test_rejects_private_192(self):
        """拒绝 192.168.x.x 私有 IP"""
        ok, reason = validate_fetch_url("http://192.168.1.1/page")
        assert not ok

    def test_rejects_loopback(self):
        """拒绝 127.0.0.1 回环地址"""
        ok, reason = validate_fetch_url("http://127.0.0.1:8080/admin")
        assert not ok

    def test_rejects_non_http(self):
        """拒绝非 http/https 协议"""
        ok, reason = validate_fetch_url("ftp://example.com/file")
        assert not ok
        assert "不允许的协议" in reason

    def test_rejects_file_scheme(self):
        """拒绝 file:// 协议"""
        ok, reason = validate_fetch_url("file:///etc/passwd")
        assert not ok

    def test_rejects_no_hostname(self):
        """拒绝无主机名 URL"""
        ok, reason = validate_fetch_url("http:///path")
        assert not ok

    def test_allows_public_https(self):
        """放行公网 HTTPS — 使用 IP 直连避免本地 DNS 干扰"""
        # 直接用知名公网 IP 绕过本地 DNS 解析差异
        ok, reason = validate_fetch_url("https://1.1.1.1/")
        assert ok, f"公网 URL 被拒绝: {reason}"


class TestFetchContent:
    """fetch_content 聚合测试"""

    @pytest.mark.asyncio
    async def test_unknown_provider(self):
        """未知提供者返回全部失败"""
        resp = await fetch_content(
            urls=["https://example.com"],
            providers=["nonexistent"],
            skip_ssrf_check=True,
        )
        assert resp.total_failed == 1
        assert resp.total_ok == 0
        assert "未知提供者" in resp.results[0].error

    @pytest.mark.asyncio
    async def test_ssrf_block_mixed(self):
        """SSRF 校验拦截部分 URL，通过的继续抓取"""
        resp = await fetch_content(
            urls=["http://127.0.0.1/admin", "https://nonexistent-domain-xyzzy.invalid/page"],
            providers=["builtin"],
        )
        # 至少 127.0.0.1 会被 SSRF 拦截
        ssrf_blocked = [r for r in resp.results if "SSRF" in (r.error or "")]
        assert len(ssrf_blocked) >= 1

    @pytest.mark.asyncio
    async def test_empty_urls_after_ssrf(self):
        """所有 URL 被 SSRF 拦截时直接返回"""
        resp = await fetch_content(
            urls=["http://127.0.0.1/a", "http://10.0.0.1/b"],
            providers=["builtin"],
        )
        assert resp.total_ok == 0
        assert resp.total_failed >= 2

    @pytest.mark.asyncio
    async def test_default_provider_is_builtin(self):
        """默认提供者为 builtin"""
        resp = await fetch_content(
            urls=["http://10.0.0.1/x"],
        )
        # 全部被 SSRF 拦截，但 provider 应为 builtin
        assert resp.provider == "builtin"
