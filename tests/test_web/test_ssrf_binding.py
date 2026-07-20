"""连接级 SSRF 防护回归测试。"""

from __future__ import annotations

import asyncio
import socket
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import httpx
import pytest

from souwen.core.exceptions import SourceUnavailableError
from souwen.core.scraper.base import BaseScraper
from souwen.web.builtin import BuiltinFetcherClient
from souwen.web.fetch import ResolvedFetchTarget, resolve_fetch_target
from souwen.web.links import extract_links
from souwen.web.newspaper_fetcher import NewspaperFetcherClient
from souwen.web.readability_fetcher import ReadabilityFetcherClient
from souwen.web.sitemap import parse_sitemap


pytestmark = pytest.mark.usefixtures("mock_public_dns")


def _addrinfo(address: str, port: int = 443) -> tuple[Any, ...]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))


def _patch_safe_client_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: httpx.AsyncBaseTransport | Any,
) -> list[httpx.AsyncClient]:
    """Route every lazily-created safe client through one deterministic transport."""

    from souwen.core.scraper import base as base_module

    real_async_client = httpx.AsyncClient
    transport = (
        handler if isinstance(handler, httpx.AsyncBaseTransport) else httpx.MockTransport(handler)
    )
    clients: list[httpx.AsyncClient] = []

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        # A configured proxy installs protocol mounts that bypass a supplied transport.
        # The harness validates the target request itself, so remove proxy routing here.
        kwargs.pop("proxy", None)
        kwargs["transport"] = transport
        client = real_async_client(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(base_module.httpx, "AsyncClient", factory)
    return clients


def test_resolver_fails_closed_on_mixed_public_private_answers(monkeypatch):
    """任一 DNS answer 命中私网时拒绝整个目标。"""

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            _addrinfo("1.1.1.1"),
            _addrinfo("169.254.169.254"),
        ],
    )

    target, reason = resolve_fetch_target("https://example.com/resource")

    assert target is None
    assert "内部/私有" in reason


def test_resolver_builds_ip_literal_target_with_original_host_and_sni(monkeypatch):
    """解析结果同时携带 IP connect URL、原 Host 与 HTTPS SNI。"""

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [_addrinfo("1.1.1.1", 8443)],
    )

    target, reason = resolve_fetch_target("https://example.com:8443/path?q=1")

    assert reason == ""
    assert target == ResolvedFetchTarget(
        original_url="https://example.com:8443/path?q=1",
        connect_url="https://1.1.1.1:8443/path?q=1",
        host_header="example.com:8443",
        sni_hostname="example.com",
    )


@pytest.mark.asyncio
async def test_resolver_idna_normalizes_dns_host_header_and_sni(monkeypatch):
    """Unicode IDN 必须在 DNS、Host 与 SNI 边界规范化为 ASCII。"""

    dns_hosts: list[str] = []

    def resolve_idn(host: str, *_args, **_kwargs):
        dns_hosts.append(host)
        return [_addrinfo("1.1.1.1")]

    requests: list[tuple[str, str, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                str(request.url),
                request.headers["host"],
                request.extensions.get("sni_hostname"),
            )
        )
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(socket, "getaddrinfo", resolve_idn)
    scraper = BaseScraper(
        min_delay=0,
        max_delay=0,
        max_retries=1,
        use_curl_cffi=False,
        follow_redirects=False,
    )
    _patch_safe_client_transport(monkeypatch, handler)

    async with scraper:
        response = await scraper._fetch_with_safe_redirects("https://bücher.example/article")

    assert response.status_code == 200
    assert dns_hosts == ["xn--bcher-kva.example"]
    assert requests == [
        ("https://1.1.1.1/article", "xn--bcher-kva.example", "xn--bcher-kva.example")
    ]


def test_resolver_formats_ipv6_connect_url_and_host_header(monkeypatch):
    """IPv6 DNS answer 使用方括号 connect URL，并保留原 hostname/port。"""

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [_addrinfo("2606:4700:4700::1111", 8443)],
    )

    target, reason = resolve_fetch_target("https://ipv6.example:8443/path")

    assert reason == ""
    assert target == ResolvedFetchTarget(
        original_url="https://ipv6.example:8443/path",
        connect_url="https://[2606:4700:4700::1111]:8443/path",
        host_header="ipv6.example:8443",
        sni_hostname="ipv6.example",
    )


def test_resolver_fails_closed_on_malformed_dns_answer(monkeypatch):
    """非标准 resolver 结果不能绕过地址分类。"""

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ())],
    )

    target, reason = resolve_fetch_target("https://example.com/resource")

    assert target is None
    assert reason == "DNS 返回无效地址"


@pytest.mark.asyncio
async def test_base_scraper_retries_only_the_pinned_ip(monkeypatch):
    """首次解析后即使 DNS 变化，retry 也不会回到 hostname。"""

    dns_calls = 0

    def rebind_after_first_lookup(*_args, **_kwargs):
        nonlocal dns_calls
        dns_calls += 1
        if dns_calls > 1:
            return [_addrinfo("127.0.0.1")]
        return [_addrinfo("1.1.1.1")]

    async def no_sleep(_delay: float) -> None:
        return None

    requests: list[tuple[str, str, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                str(request.url),
                request.headers["host"],
                request.extensions.get("sni_hostname"),
            )
        )
        status_code = 500 if len(requests) == 1 else 200
        return httpx.Response(status_code, text="ok")

    monkeypatch.setattr(socket, "getaddrinfo", rebind_after_first_lookup)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    scraper = BaseScraper(
        min_delay=0,
        max_delay=0,
        max_retries=2,
        use_curl_cffi=False,
        follow_redirects=False,
    )
    _patch_safe_client_transport(monkeypatch, handler)
    async with scraper:
        response = await scraper._fetch_with_safe_redirects("https://example.com/start")

    assert response.status_code == 200
    assert dns_calls == 1
    assert requests == [
        ("https://1.1.1.1/start", "example.com", "example.com"),
        ("https://1.1.1.1/start", "example.com", "example.com"),
    ]


@pytest.mark.asyncio
async def test_base_scraper_does_not_send_private_redirect(monkeypatch):
    """公网首跳重定向到私网时，只允许首跳到达 transport。"""

    sent_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent_urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/admin"},
        )

    scraper = BaseScraper(
        min_delay=0,
        max_delay=0,
        max_retries=1,
        use_curl_cffi=False,
        follow_redirects=False,
    )
    _patch_safe_client_transport(monkeypatch, handler)
    async with scraper:
        with pytest.raises(SourceUnavailableError, match="重定向目标被拦截"):
            await scraper._fetch_with_safe_redirects("https://example.com/start")

    assert sent_urls == ["https://1.1.1.1/start"]


@pytest.mark.asyncio
async def test_proxy_client_receives_only_ip_literal_connect_target(monkeypatch):
    """配置代理时仍把已校验 IP 交给 HTTP client，而非原 hostname。"""

    from souwen.core.scraper import base as base_module

    target, reason = resolve_fetch_target("https://example.com/private-proxy-test")
    assert target is not None, reason

    captured: dict[str, Any] = {}

    class CapturingAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        async def request(self, method: str, url: str, **kwargs: Any) -> SimpleNamespace:
            captured["request"] = (method, url, kwargs)
            return SimpleNamespace(status_code=200, headers={})

        async def aclose(self) -> None:
            return None

    scraper = BaseScraper(use_curl_cffi=False, follow_redirects=False)
    scraper._proxy = "socks5://proxy.example:1080"
    scraper._safe_httpx_clients = {}
    monkeypatch.setattr(base_module.httpx, "AsyncClient", CapturingAsyncClient)

    try:
        await scraper._do_resolved_request(
            "GET",
            target,
            None,
            {"Host": target.host_header},
        )
    finally:
        await scraper.close()

    assert captured["init"]["proxy"] == "socks5://proxy.example:1080"
    _method, connect_url, request_kwargs = captured["request"]
    assert connect_url == "https://1.1.1.1/private-proxy-test"
    assert request_kwargs["headers"]["Host"] == "example.com"
    assert request_kwargs["extensions"] == {"sni_hostname": "example.com"}
    assert request_kwargs["follow_redirects"] is False


@pytest.mark.asyncio
async def test_safe_clients_are_isolated_by_original_authority(monkeypatch):
    """同一 IP 上的不同 hostname 不共享 connection pool 或 cookie jar。"""

    from souwen.core.scraper import base as base_module

    created_clients: list[Any] = []
    requests: list[tuple[int, str, str]] = []

    class CapturingAsyncClient:
        def __init__(self, **_kwargs: Any) -> None:
            self.client_id = len(created_clients)
            created_clients.append(self)

        async def request(self, method: str, url: str, **kwargs: Any) -> SimpleNamespace:
            requests.append((self.client_id, url, kwargs["headers"]["Host"]))
            return SimpleNamespace(status_code=200, headers={})

        async def aclose(self) -> None:
            return None

    scraper = BaseScraper(use_curl_cffi=False, follow_redirects=False)
    monkeypatch.setattr(base_module.httpx, "AsyncClient", CapturingAsyncClient)
    targets: list[ResolvedFetchTarget] = []
    for url in (
        "https://a.example/one",
        "https://b.example/two",
        "https://a.example/three",
    ):
        target, reason = resolve_fetch_target(url)
        assert target is not None, reason
        targets.append(target)

    try:
        await asyncio.gather(
            scraper._do_resolved_request("GET", targets[0], None, {"Host": "a.example"}),
            scraper._do_resolved_request("GET", targets[1], None, {"Host": "b.example"}),
        )
        await scraper._do_resolved_request("GET", targets[2], None, {"Host": "a.example"})
    finally:
        await scraper.close()

    assert len(created_clients) == 2
    assert requests == [
        (0, "https://1.1.1.1/one", "a.example"),
        (1, "https://1.1.1.1/two", "b.example"),
        (0, "https://1.1.1.1/three", "a.example"),
    ]


@pytest.mark.asyncio
async def test_cross_origin_redirect_isolates_headers_host_sni_and_client(monkeypatch):
    """跨 origin 跳转不转发配置/caller headers，并更新 Host、SNI 和 client。"""

    requests: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            {
                "url": str(request.url),
                "host": request.headers.get_list("host"),
                "authorization": request.headers.get("authorization"),
                "cookie": request.headers.get("cookie"),
                "api_key": request.headers.get("x-api-key"),
                "sni": request.extensions.get("sni_hostname"),
            }
        )
        if len(requests) == 1:
            return httpx.Response(302, headers={"location": "https://b.example/final"})
        return httpx.Response(200, text="ok")

    scraper = BaseScraper(
        min_delay=0,
        max_delay=0,
        max_retries=1,
        use_curl_cffi=False,
        follow_redirects=False,
    )
    scraper._channel_headers = {
        "authorization": "Bearer channel-secret",
        "x-api-key": "channel-api-secret",
        "host": "attacker.invalid",
    }
    clients = _patch_safe_client_transport(monkeypatch, handler)

    async with scraper:
        response = await scraper._fetch_with_safe_redirects(
            "https://a.example/start",
            headers={"Cookie": "session=caller-secret", "HOST": "attacker.invalid"},
        )

    assert len(clients) == 2
    assert requests == [
        {
            "url": "https://1.1.1.1/start",
            "host": ["a.example"],
            "authorization": "Bearer channel-secret",
            "cookie": "session=caller-secret",
            "api_key": "channel-api-secret",
            "sni": "a.example",
        },
        {
            "url": "https://1.1.1.1/final",
            "host": ["b.example"],
            "authorization": None,
            "cookie": None,
            "api_key": None,
            "sni": "b.example",
        },
    ]
    assert response.extensions["souwen_final_url"] == "https://b.example/final"


@pytest.mark.asyncio
async def test_builtin_and_robots_requests_use_bound_transport(monkeypatch):
    """builtin 初始抓取与 robots.txt 都必须通过 IP-pinned transport。"""

    from souwen.web import builtin as builtin_module

    fake_protego = ModuleType("protego")

    class FakeProtego:
        @classmethod
        def parse(cls, _text: str) -> "FakeProtego":
            return cls()

        def can_fetch(self, _url: str, _user_agent: str) -> bool:
            return True

    fake_protego.Protego = FakeProtego  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "protego", fake_protego)
    monkeypatch.setattr(builtin_module, "_HAS_PROTEGO", True)

    requests: list[tuple[str, str, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                str(request.url),
                request.headers["host"],
                request.extensions.get("sni_hostname"),
            )
        )
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        html = (
            "<html><body><article><p>" + ("Bound content. " * 30) + "</p></article></body></html>"
        )
        return httpx.Response(200, text=html)

    client = BuiltinFetcherClient(respect_robots_txt=True)
    _patch_safe_client_transport(monkeypatch, handler)
    async with client:
        result = await client.fetch("https://example.com/article")

    assert result.error is None
    assert requests == [
        ("https://1.1.1.1/robots.txt", "example.com", "example.com"),
        ("https://1.1.1.1/article", "example.com", "example.com"),
    ]


@pytest.mark.asyncio
async def test_links_and_sitemap_paths_receive_bound_targets(monkeypatch):
    """`/links` 与 `/sitemap` 的应用函数只把 IP literal 交给 transport。"""

    captured: list[ResolvedFetchTarget] = []

    async def fake_resolved_request(
        _self: BaseScraper,
        method: str,
        target: ResolvedFetchTarget,
        _params: dict[str, Any] | None,
        headers: dict[str, str],
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        del data
        captured.append(target)
        if target.original_url.endswith("sitemap.xml"):
            content = (
                b'<?xml version="1.0" encoding="UTF-8"?>'
                b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                b"<url><loc>https://example.com/page</loc></url></urlset>"
            )
        else:
            content = b'<html><body><a href="/next">Next</a></body></html>'
        request = httpx.Request(
            method,
            target.connect_url,
            headers=headers,
            extensions={"sni_hostname": target.sni_hostname},
        )
        return httpx.Response(200, content=content, request=request)

    monkeypatch.setattr(BaseScraper, "_do_resolved_request", fake_resolved_request)

    links = await extract_links("https://example.com/source")
    sitemap = await parse_sitemap("https://example.com/sitemap.xml")

    assert links.error is None
    assert links.final_url == "https://example.com/source"
    assert sitemap.total == 1
    assert [target.connect_url for target in captured] == [
        "https://1.1.1.1/source",
        "https://1.1.1.1/sitemap.xml",
    ]
    assert all(target.host_header == "example.com" for target in captured)
    assert all(target.sni_hostname == "example.com" for target in captured)


@pytest.mark.asyncio
async def test_readability_uses_bound_transport_and_preserves_public_redirect(monkeypatch):
    """readability initial/redirect 请求均绑定 IP，final_url 保留逻辑 hostname。"""

    from souwen.web import readability_fetcher as readability_module

    monkeypatch.setattr(readability_module, "_HAS_READABILITY", True)
    monkeypatch.setattr(
        readability_module,
        "_extract_with_readability_sync",
        lambda _html, _url: {
            "content": "readability bound content " * 20,
            "title": "Bound",
            "content_format": "text",
        },
    )
    requests: list[tuple[str, str, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                str(request.url),
                request.headers["host"],
                request.extensions.get("sni_hostname"),
            )
        )
        if len(requests) == 1:
            return httpx.Response(302, headers={"location": "https://final.example/article"})
        return httpx.Response(200, text="<html>" + ("Readable content. " * 20) + "</html>")

    client = ReadabilityFetcherClient()
    _patch_safe_client_transport(monkeypatch, handler)
    async with client:
        result = await client.fetch("https://start.example/article")

    assert result.error is None
    assert result.final_url == "https://final.example/article"
    assert requests == [
        ("https://1.1.1.1/article", "start.example", "start.example"),
        ("https://1.1.1.1/article", "final.example", "final.example"),
    ]


@pytest.mark.asyncio
async def test_readability_does_not_send_private_redirect(monkeypatch):
    """readability 公网首跳后的私网 Location 不到达 transport。"""

    from souwen.web import readability_fetcher as readability_module

    monkeypatch.setattr(readability_module, "_HAS_READABILITY", True)
    sent_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent_urls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/metadata"})

    client = ReadabilityFetcherClient()
    _patch_safe_client_transport(monkeypatch, handler)
    async with client:
        result = await client.fetch("https://start.example/article")

    assert result.error is not None
    assert "SSRF" in result.error
    assert sent_urls == ["https://1.1.1.1/article"]


@pytest.mark.asyncio
async def test_newspaper_final_url_does_not_expose_bound_ip(monkeypatch):
    """newspaper 对外返回 public redirect URL，而不是 transport IP。"""

    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if len(requests) == 1:
            return httpx.Response(302, headers={"location": "https://news-final.example/story"})
        return httpx.Response(200, text="<html>" + ("Newspaper content. " * 20) + "</html>")

    article = SimpleNamespace(
        text="Parsed newspaper content " * 20,
        title="Story",
        authors=[],
        publish_date=None,
        keywords=[],
        top_image="",
        meta_description="",
    )
    client = NewspaperFetcherClient()
    client._newspaper = SimpleNamespace(article=lambda *_args, **_kwargs: article)
    _patch_safe_client_transport(monkeypatch, handler)
    try:
        result = await client.fetch("https://news-start.example/story")
    finally:
        await client.close()

    assert result.error is None
    assert result.final_url == "https://news-final.example/story"
    assert "1.1.1.1" not in result.final_url
    assert requests == ["https://1.1.1.1/story", "https://1.1.1.1/story"]
