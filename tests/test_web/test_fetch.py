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
import socket
from types import SimpleNamespace

import pytest

from souwen.core.exceptions import SourceUnavailableError
from souwen.core.scraper.base import BaseScraper
from souwen.editions import EditionError
from souwen.models import FetchResponse, FetchResult
from souwen.web.fetch import fetch_content, register_fetch_handler, validate_fetch_url


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

    def test_rejects_localhost_trailing_dot(self):
        """拒绝带 DNS 尾点的 localhost 主机名。"""
        ok, reason = validate_fetch_url("http://localhost./admin")
        assert not ok
        assert "本地主机" in reason

    @pytest.mark.parametrize(
        "url",
        [
            "http://[::ffff:127.0.0.1]/",
            "http://[::ffff:10.0.0.1]/",
            "http://[64:ff9b::7f00:1]/",
            "http://[2002:7f00:1::]/",
        ],
    )
    def test_rejects_ipv6_embedded_private_addresses(self, url):
        """拒绝 IPv4-mapped/NAT64/6to4 形式包装的内部 IPv4 地址。"""
        ok, reason = validate_fetch_url(url)
        assert not ok
        assert "内部/私有" in reason

    @pytest.mark.parametrize(
        "url",
        [
            "http://0177.0.0.1/",
            "http://00000177.0.0.1/",
            "http://008.0.0.1/",
            "http://01.1.1.1/",
            "http://0177.1/",
            "http://1.1.1/",
            "http://1/",
            "http://2130706433/",
            "http://0x7f000001/",
            "http://0x08000001/",
            "http://0300.0250.0001.0001/",
        ],
    )
    def test_rejects_legacy_ipv4_numeric_hosts_before_dns(self, monkeypatch, url):
        """拒绝 resolver 可能接受的旧式 IPv4 数字写法。"""

        def fail_getaddrinfo(*_args, **_kwargs):
            raise AssertionError("legacy IPv4 literal should be blocked before DNS")

        monkeypatch.setattr(socket, "getaddrinfo", fail_getaddrinfo)

        ok, reason = validate_fetch_url(url)
        assert not ok
        assert "非规范 IPv4 数字写法" in reason

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

    def test_rejects_direct_fake_ip_range(self):
        """直连 fake-IP/benchmark 保留网段仍应拒绝。"""
        ok, reason = validate_fetch_url("https://198.18.1.47/")
        assert not ok
        assert "内部/私有" in reason

    def test_allows_domain_resolved_to_fake_ip_range(self, monkeypatch):
        """允许 Clash/fake-IP DNS 将公网域名解析到 198.18.0.0/15。"""

        def fake_getaddrinfo(*_args, **_kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.1.47", 443))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        ok, reason = validate_fetch_url("https://example.com/")
        assert ok, f"fake-IP DNS 域名被拒绝: {reason}"

    def test_rejects_domain_resolved_to_ipv4_mapped_loopback(self, monkeypatch):
        """DNS 返回 IPv4-mapped IPv6 loopback 时也必须拒绝。"""

        def fake_getaddrinfo(*_args, **_kwargs):
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 443))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        ok, reason = validate_fetch_url("https://example.com/")
        assert not ok
        assert "内部/私有" in reason


class TestSafeRedirects:
    """通用抓取层逐跳 SSRF 防护测试"""

    @pytest.mark.asyncio
    async def test_base_scraper_blocks_private_redirect_target(self):
        scraper = BaseScraper.__new__(BaseScraper)

        async def fake_fetch(url, **_kwargs):
            return SimpleNamespace(
                status_code=302,
                headers={"location": "http://127.0.0.1/admin"},
                url=url,
            )

        scraper._fetch = fake_fetch

        with pytest.raises(SourceUnavailableError, match="SSRF"):
            await scraper._fetch_with_safe_redirects("https://example.com/start")


class TestFetchContent:
    """fetch_content 聚合测试"""

    @staticmethod
    def _response(provider: str, urls: list[str], failed: set[str] | None = None) -> FetchResponse:
        failed = failed or set()
        results = [
            FetchResult(
                url=url,
                final_url=url,
                source=provider,
                title=f"{provider} title",
                content=f"{provider} content",
                error="boom" if url in failed else None,
            )
            for url in urls
        ]
        ok_count = sum(1 for result in results if result.error is None)
        return FetchResponse(
            urls=list(urls),
            results=results,
            total=len(results),
            total_ok=ok_count,
            total_failed=len(results) - ok_count,
            provider=provider,
            providers=[provider],
        )

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
        assert resp.providers == ["nonexistent"]
        assert resp.strategy == "fallback"
        assert "未知提供者" in resp.results[0].error

    @pytest.mark.asyncio
    async def test_full_fetch_provider_requires_full_edition(self, monkeypatch):
        """已知 full provider 在默认 pro edition 下应被执行层拦截。"""
        monkeypatch.setenv("SOUWEN_EDITION", "pro")

        with pytest.raises(EditionError, match="arxiv_fulltext.*requires edition=full"):
            await fetch_content(
                urls=["https://arxiv.org/abs/2301.00001"],
                providers=["arxiv_fulltext"],
                skip_ssrf_check=True,
            )

    @pytest.mark.asyncio
    async def test_string_url_and_provider_are_normalized(self, clean_fetch_handlers):
        """Python API 误传单个字符串时应归一化为单元素列表。"""
        calls: list[tuple[list[str], float]] = []

        async def primary(urls, timeout, **_kwargs):
            calls.append((list(urls), timeout))
            return self._response("primary", list(urls))

        register_fetch_handler("primary", primary)

        resp = await fetch_content(
            urls=" https://example.com/a ",
            providers=" primary ",
            skip_ssrf_check=True,
        )

        assert calls == [(["https://example.com/a"], 30.0)]
        assert resp.urls == ["https://example.com/a"]
        assert resp.provider == "primary"
        assert resp.providers == ["primary"]
        assert resp.total_ok == 1

    @pytest.mark.parametrize(
        "kwargs, message",
        [
            ({"urls": {"url": "https://example.com"}}, "urls 必须是字符串或字符串列表"),
            ({"urls": [" "]}, "urls 必须是非空字符串或非空字符串列表"),
            (
                {"urls": ["https://example.com"], "providers": {"name": "builtin"}},
                "providers 必须是字符串或字符串列表",
            ),
            (
                {"urls": ["https://example.com"], "providers": [" "]},
                "providers 必须是非空字符串或非空字符串列表",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_invalid_url_or_provider_arguments_raise_clear_error(self, kwargs, message):
        """公开 Python API 对非法 urls/providers 入参应给出清晰错误。"""
        with pytest.raises(ValueError, match=message):
            await fetch_content(**kwargs)

    @pytest.mark.asyncio
    async def test_fallback_retries_only_failed_urls(self, clean_fetch_handlers):
        """fallback 应只把失败 URL 交给后续 provider 补抓。"""
        calls: list[tuple[str, list[str]]] = []
        urls = [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
        ]

        async def primary(urls, timeout, **_kwargs):
            calls.append(("primary", list(urls)))
            return self._response("primary", list(urls), failed={"https://example.com/c"})

        async def backup(urls, timeout, **_kwargs):
            calls.append(("backup", list(urls)))
            return self._response("backup", list(urls))

        register_fetch_handler("primary", primary)
        register_fetch_handler("backup", backup)

        resp = await fetch_content(
            urls=urls,
            providers=["primary", "backup"],
            strategy="fallback",
            skip_ssrf_check=True,
        )

        assert calls == [
            ("primary", urls),
            ("backup", ["https://example.com/c"]),
        ]
        assert resp.total == 3
        assert resp.total_ok == 3
        assert resp.provider is None
        assert resp.providers == ["primary", "backup"]
        assert resp.strategy == "fallback"
        assert [result.source for result in resp.results] == ["primary", "primary", "backup"]
        assert resp.meta["attempted"] == {
            "https://example.com/a": ["primary"],
            "https://example.com/b": ["primary"],
            "https://example.com/c": ["primary", "backup"],
        }
        assert resp.meta["selected_provider"] == {
            "https://example.com/a": "primary",
            "https://example.com/b": "primary",
            "https://example.com/c": "backup",
        }

    @pytest.mark.asyncio
    async def test_fanout_returns_all_provider_results(self, clean_fetch_handlers):
        """fanout 应并发执行所有 provider，并返回所有 provider 结果。"""
        calls: list[tuple[str, list[str]]] = []
        urls = ["https://example.com/a", "https://example.com/b"]

        async def left(urls, timeout, **_kwargs):
            calls.append(("left", list(urls)))
            return self._response("left", list(urls))

        async def right(urls, timeout, **_kwargs):
            calls.append(("right", list(urls)))
            return self._response("right", list(urls))

        register_fetch_handler("left", left)
        register_fetch_handler("right", right)

        resp = await fetch_content(
            urls=urls,
            providers=["left", "right"],
            strategy="fanout",
            skip_ssrf_check=True,
        )

        assert sorted(calls) == [("left", urls), ("right", urls)]
        assert resp.total == 4
        assert resp.total_ok == 4
        assert resp.provider is None
        assert resp.providers == ["left", "right"]
        assert resp.strategy == "fanout"
        assert [result.source for result in resp.results] == ["left", "left", "right", "right"]
        assert resp.meta["attempted"] == {
            "https://example.com/a": ["left", "right"],
            "https://example.com/b": ["left", "right"],
        }

    @pytest.mark.asyncio
    async def test_fanout_reports_missing_provider_results(self, clean_fetch_handlers):
        """fanout 中 provider 漏返回某个 URL 时应补失败项，避免 report 少行。"""
        urls = ["https://example.com/a", "https://example.com/b"]

        async def partial(urls, timeout, **_kwargs):
            return self._response("partial", [list(urls)[0]])

        async def complete(urls, timeout, **_kwargs):
            return self._response("complete", list(urls))

        register_fetch_handler("partial", partial)
        register_fetch_handler("complete", complete)

        resp = await fetch_content(
            urls=urls,
            providers=["partial", "complete"],
            strategy="fanout",
            skip_ssrf_check=True,
        )

        assert resp.total == 4
        missing = [
            result
            for result in resp.results
            if result.source == "partial" and result.url == "https://example.com/b"
        ]
        assert len(missing) == 1
        assert missing[0].error == "partial 未返回该 URL 的抓取结果"

    @pytest.mark.asyncio
    async def test_fanout_does_not_duplicate_ssrf_failures(self, clean_fetch_handlers):
        """fanout 不应按 provider 数量放大 SSRF 拦截失败。"""
        calls: list[tuple[str, list[str]]] = []

        async def first(urls, timeout, **_kwargs):
            calls.append(("first", list(urls)))
            return self._response("first", list(urls))

        async def second(urls, timeout, **_kwargs):
            calls.append(("second", list(urls)))
            return self._response("second", list(urls))

        register_fetch_handler("first", first)
        register_fetch_handler("second", second)

        resp = await fetch_content(
            urls=["http://127.0.0.1/admin", "https://1.1.1.1/"],
            providers=["first", "second"],
            strategy="fanout",
        )

        ssrf_failures = [result for result in resp.results if "SSRF" in (result.error or "")]
        assert len(ssrf_failures) == 1
        assert resp.meta["ssrf_blocked"] == 1
        assert sorted(calls) == [
            ("first", ["https://1.1.1.1/"]),
            ("second", ["https://1.1.1.1/"]),
        ]

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
        assert resp.providers == ["builtin"]
        assert resp.strategy == "fallback"

    @pytest.mark.asyncio
    async def test_arxiv_fulltext_provider_dispatches(self, monkeypatch):
        """arxiv_fulltext provider 应从 arxiv URL 提取 paper_id 并复用现有 client。"""
        monkeypatch.setenv("SOUWEN_EDITION", "full")
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
    async def test_arxiv_fulltext_rejects_non_arxiv_urls(self, monkeypatch):
        """arxiv_fulltext provider 对非 arxiv URL 返回 provider 级错误。"""
        monkeypatch.setenv("SOUWEN_EDITION", "full")
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
        monkeypatch.setenv("SOUWEN_EDITION", "full")

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
        monkeypatch.setenv("SOUWEN_EDITION", "full")
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

    @pytest.mark.asyncio
    async def test_metaso_scales_global_timeout_with_batch_size(
        self,
        monkeypatch,
        clean_fetch_handlers,
    ):
        """metaso Reader 逐 URL 抓取，provider 级总超时应按 URL 数量伸缩。"""
        captured_timeouts: list[float] = []
        original_wait_for = asyncio.wait_for

        async def recording_wait_for(awaitable, timeout):
            captured_timeouts.append(timeout)
            return await original_wait_for(awaitable, timeout)

        async def metaso_handler(urls, timeout, **_kwargs):
            return self._response("metaso", list(urls))

        import souwen.web.fetch as fetch_mod

        register_fetch_handler("metaso", metaso_handler, override=True)
        monkeypatch.setattr(fetch_mod.asyncio, "wait_for", recording_wait_for)

        urls = [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
        ]
        resp = await fetch_content(
            urls=urls,
            providers=["metaso"],
            timeout=2.0,
            skip_ssrf_check=True,
        )

        assert resp.total_ok == 3
        assert captured_timeouts == pytest.approx([16.0])
