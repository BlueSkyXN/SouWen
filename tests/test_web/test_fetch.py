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

import asyncio

import pytest

from souwen.models import FetchResult
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

    @pytest.mark.asyncio
    async def test_arxiv_fulltext_provider_dispatches(self, monkeypatch):
        """arxiv_fulltext provider 应从 arxiv URL 提取 paper_id 并复用现有 client。"""
        calls: list[str] = []

        class FakeArxivFulltextClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def get_fulltext(self, paper_id: str):
                calls.append(paper_id)
                return FetchResult(
                    url=f"https://arxiv.org/abs/{paper_id}",
                    final_url=f"https://arxiv.org/html/{paper_id}",
                    title="stub title",
                    content="stub content",
                    content_format="text",
                    source="arxiv_fulltext",
                )

        import souwen.paper.arxiv_fulltext as arxiv_fulltext_mod

        monkeypatch.setattr(
            arxiv_fulltext_mod,
            "ArxivFulltextClient",
            FakeArxivFulltextClient,
        )

        resp = await fetch_content(
            urls=["https://arxiv.org/abs/2301.00001v2"],
            providers=["arxiv_fulltext"],
            skip_ssrf_check=True,
        )

        assert calls == ["2301.00001v2"]
        assert resp.provider == "arxiv_fulltext"
        assert resp.total_ok == 1
        assert resp.results[0].url == "https://arxiv.org/abs/2301.00001v2"
        assert resp.results[0].final_url == "https://arxiv.org/html/2301.00001v2"

    @pytest.mark.asyncio
    async def test_arxiv_fulltext_rejects_non_arxiv_urls(self):
        """arxiv_fulltext provider 对非 arxiv URL 返回 provider 级错误。"""
        resp = await fetch_content(
            urls=["https://example.com/paper"],
            providers=["arxiv_fulltext"],
            skip_ssrf_check=True,
        )

        assert resp.total_ok == 0
        assert resp.total_failed == 1
        assert resp.results[0].error == (
            "arxiv_fulltext 仅支持 arxiv.org 的 /abs/、/html/ 或 /pdf/ URL"
        )

    @pytest.mark.asyncio
    async def test_arxiv_fulltext_enforces_per_url_timeout(self, monkeypatch):
        """arxiv_fulltext 应对每个 URL 单独应用用户请求的 timeout。"""

        class SlowArxivFulltextClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def get_fulltext(self, paper_id: str):
                await asyncio.sleep(0.05)
                return FetchResult(
                    url=f"https://arxiv.org/abs/{paper_id}",
                    final_url=f"https://arxiv.org/html/{paper_id}",
                    title="slow title",
                    content="slow content",
                    content_format="text",
                    source="arxiv_fulltext",
                )

        import souwen.paper.arxiv_fulltext as arxiv_fulltext_mod

        monkeypatch.setattr(
            arxiv_fulltext_mod,
            "ArxivFulltextClient",
            SlowArxivFulltextClient,
        )

        resp = await fetch_content(
            urls=["https://arxiv.org/abs/2301.00001"],
            providers=["arxiv_fulltext"],
            timeout=0.01,
            skip_ssrf_check=True,
        )

        assert resp.total_ok == 0
        assert resp.total_failed == 1
        assert "超时" in (resp.results[0].error or "")

    @pytest.mark.asyncio
    async def test_arxiv_fulltext_scales_global_timeout_with_batch_size(self, monkeypatch):
        """arxiv_fulltext 的 provider 级总超时应按 URL 数量伸缩。"""
        captured_timeouts: list[float] = []
        original_wait_for = asyncio.wait_for

        async def recording_wait_for(awaitable, timeout):
            captured_timeouts.append(timeout)
            return await original_wait_for(awaitable, timeout)

        class FastArxivFulltextClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def get_fulltext(self, paper_id: str):
                return FetchResult(
                    url=f"https://arxiv.org/abs/{paper_id}",
                    final_url=f"https://arxiv.org/html/{paper_id}",
                    title="fast title",
                    content="fast content",
                    content_format="text",
                    source="arxiv_fulltext",
                )

        import souwen.paper.arxiv_fulltext as arxiv_fulltext_mod
        import souwen.web.fetch as fetch_mod

        monkeypatch.setattr(
            arxiv_fulltext_mod,
            "ArxivFulltextClient",
            FastArxivFulltextClient,
        )
        monkeypatch.setattr(fetch_mod.asyncio, "wait_for", recording_wait_for)

        urls = [
            "https://arxiv.org/abs/2301.00001",
            "https://arxiv.org/abs/2301.00002",
            "https://arxiv.org/abs/2301.00003",
        ]
        resp = await fetch_content(
            urls=urls,
            providers=["arxiv_fulltext"],
            timeout=2.0,
            skip_ssrf_check=True,
        )

        assert resp.total_ok == 3
        assert captured_timeouts[0] == pytest.approx(16.0)
        assert captured_timeouts[1:] == pytest.approx([2.0, 2.0, 2.0])
