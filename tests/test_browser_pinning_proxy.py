"""Local TCP proof that browser egress uses the validated IP and exact origin.

迁自 Browser Worker 时代的 test_browser_worker_pinning_proxy.py；被测对象换成
主进程内的 browser_pinning_proxy（SPEC 10：连接级 SSRF 约束等价保留）。
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

from souwen.common_runtime.provider_support.browser_pinning_proxy import PinnedLoopbackProxy
from souwen.common_runtime.security import ResolvedFetchTarget


@pytest.mark.asyncio
async def test_pinning_proxy_connects_to_resolved_ip_and_rejects_other_origin() -> None:
    connections = 0

    async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal connections
        connections += 1
        request = await reader.readuntil(b"\r\n\r\n")
        assert request.startswith(b"GET /page?x=1 HTTP/1.1\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        await writer.drain()
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()

    upstream_server = await asyncio.start_server(upstream, "127.0.0.1", 0)
    upstream_port = int(upstream_server.sockets[0].getsockname()[1])
    target_url = f"http://example.com:{upstream_port}/page?x=1"
    pinned = ResolvedFetchTarget(
        original_url=target_url,
        connect_url=f"http://127.0.0.1:{upstream_port}/page?x=1",
        host_header=f"example.com:{upstream_port}",
        sni_hostname=None,
    )

    async def resolver(url: str):
        if url.startswith(f"http://example.com:{upstream_port}/"):
            return pinned, ""
        return None, "blocked"

    proxy = PinnedLoopbackProxy(target_url=target_url, resolver=resolver)
    await proxy.start()
    proxy_port = int(proxy.url.rsplit(":", 1)[1])
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        writer.write(
            f"GET {target_url} HTTP/1.1\r\nHost: example.com:{upstream_port}\r\n\r\n".encode()
        )
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()

        blocked_reader, blocked_writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        blocked_writer.write(
            f"GET http://other.example:{upstream_port}/ HTTP/1.1\r\n"
            f"Host: other.example:{upstream_port}\r\n\r\n".encode()
        )
        await blocked_writer.drain()
        blocked = await blocked_reader.read()
        blocked_writer.close()
        await blocked_writer.wait_closed()
    finally:
        await proxy.close()
        upstream_server.close()
        await upstream_server.wait_closed()

    assert response.endswith(b"\r\n\r\nok")
    assert blocked.startswith(b"HTTP/1.1 502 Bad Gateway")
    assert connections == 1


@pytest.mark.asyncio
async def test_pinning_proxy_connect_tunnels_tls_authority_to_validated_ip() -> None:
    async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert await reader.readexactly(4) == b"ping"
        writer.write(b"pong")
        await writer.drain()
        writer.close()

    upstream_server = await asyncio.start_server(upstream, "127.0.0.1", 0)
    upstream_port = int(upstream_server.sockets[0].getsockname()[1])
    target_url = f"https://example.com:{upstream_port}/"
    pinned = ResolvedFetchTarget(
        original_url=target_url,
        connect_url=f"https://127.0.0.1:{upstream_port}/",
        host_header=f"example.com:{upstream_port}",
        sni_hostname="example.com",
    )

    async def resolver(url: str):
        if url == target_url:
            return pinned, ""
        return None, "blocked"

    proxy = PinnedLoopbackProxy(target_url=target_url, resolver=resolver)
    await proxy.start()
    proxy_port = int(proxy.url.rsplit(":", 1)[1])
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        writer.write(
            f"CONNECT example.com:{upstream_port} HTTP/1.1\r\n"
            f"Host: example.com:{upstream_port}\r\n\r\n".encode()
        )
        await writer.drain()
        established = await reader.readuntil(b"\r\n\r\n")
        writer.write(b"ping")
        await writer.drain()
        tunneled = await reader.readexactly(4)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
        upstream_server.close()
        await upstream_server.wait_closed()

    assert established == b"HTTP/1.1 200 Connection Established\r\n\r\n"
    assert tunneled == b"pong"


@pytest.mark.asyncio
async def test_browser_page_routes_through_the_pinned_proxy(monkeypatch) -> None:
    """_validated_page must hand the browser a pinned-proxy URL, not raw egress."""

    from contextlib import asynccontextmanager

    from souwen.common_runtime.provider_support import browser_fetch
    from souwen.common_runtime.security import ResolvedFetchTarget

    seen_proxies: list[str | None] = []

    @asynccontextmanager
    async def fake_pool_page(**kwargs):
        seen_proxies.append(kwargs.get("proxy"))
        yield _StubPage()

    class _StubPage:
        url = "https://example.com/page"

        async def route(self, pattern, handler):
            self._handler = handler

        async def goto(self, url, **kwargs):
            return _StubResponse()

        async def title(self):
            return "t"

    class _StubResponse:
        status = 200

        async def all_headers(self):
            return {}

    class _StubPool:
        def page(self, **kwargs):
            return fake_pool_page(**kwargs)

    monkeypatch.setattr(browser_fetch, "_shared_pool", lambda: _StubPool())
    monkeypatch.setattr(browser_fetch, "chromium_available", lambda: True)

    resolved = ResolvedFetchTarget(
        original_url="https://example.com/page",
        connect_url="https://93.184.216.34/page",
        host_header="example.com",
        sni_hostname="example.com",
    )

    async def resolver(url: str):
        return resolved, ""

    monkeypatch.setattr(browser_fetch, "resolve_fetch_target_async", resolver)

    async with browser_fetch._validated_page(
        "https://example.com/page", timeout_seconds=5, proxy=None
    ) as (page, response):
        assert response.status == 200

    assert len(seen_proxies) == 1
    assert seen_proxies[0].startswith("http://127.0.0.1:")


@pytest.mark.asyncio
async def test_pinning_proxy_routes_through_socks5_upstream_with_ip_only() -> None:
    """上游代理（WARP 形态的 socks5）与 pinning 同时成立。

    SOCKS5 上游只收到校验后的 IP 字面量（ATYP=1/4），从不接收域名；
    SSRF 拒绝的 origin 不会到达上游。
    """

    socks_requests: list[bytes] = []

    async def socks_upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        # greeting: VER NMETHODS METHODS → 回 NO AUTH
        greeting = await reader.readexactly(2)
        assert greeting[0] == 0x05
        await reader.readexactly(greeting[1])
        writer.write(b"\x05\x00")
        await writer.drain()
        request = await reader.readexactly(4)
        atyp = request[3]
        if atyp == 0x01:
            addr = await reader.readexactly(4)
            socks_requests.append(bytes(request) + addr)
        elif atyp == 0x04:
            raw = await reader.readexactly(16)
            socks_requests.append(bytes(request) + raw)
        else:
            raise AssertionError("upstream must not receive a domain name")
        await reader.readexactly(2)  # 端口
        # 成功应答：VER REP RSV ATYP=1 BND 0.0.0.0:0
        writer.write(b"\x05\x00\x00\x01" + b"\x00" * 4 + b"\x00\x00")
        await writer.drain()
        # CONNECT 隧道内：透明转发
        data = await reader.readexactly(4)
        assert data == b"ping"
        writer.write(b"pong")
        await writer.drain()
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()

    upstream_server = await asyncio.start_server(socks_upstream, "127.0.0.1", 0)
    upstream_port = int(upstream_server.sockets[0].getsockname()[1])
    target_url = "https://example.com:443/"
    pinned = ResolvedFetchTarget(
        original_url=target_url,
        connect_url="https://93.184.216.34/",
        host_header="example.com",
        sni_hostname="example.com",
    )

    async def resolver(url: str):
        if url == target_url:
            return pinned, ""
        return None, "blocked"

    proxy = PinnedLoopbackProxy(
        target_url=target_url,
        resolver=resolver,
        upstream_proxy=f"socks5://127.0.0.1:{upstream_port}",
    )
    await proxy.start()
    proxy_port = int(proxy.url.rsplit(":", 1)[1])
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        writer.write(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
        await writer.drain()
        established = await reader.readuntil(b"\r\n\r\n")
        writer.write(b"ping")
        await writer.drain()
        tunneled = await reader.readexactly(4)
        writer.close()
        await writer.wait_closed()

        # SSRF 拒绝的 origin：502，不产生新的上游连接
        blocked_reader, blocked_writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        blocked_writer.write(b"CONNECT evil.example:443 HTTP/1.1\r\nHost: evil.example\r\n\r\n")
        await blocked_writer.drain()
        blocked = await blocked_reader.read()
        blocked_writer.close()
        await blocked_writer.wait_closed()
    finally:
        await proxy.close()
        upstream_server.close()
        await upstream_server.wait_closed()

    assert established == b"HTTP/1.1 200 Connection Established\r\n\r\n"
    assert tunneled == b"pong"
    assert blocked.startswith(b"HTTP/1.1 502")
    # 上游恰好收到一个 CONNECT 请求，目标地址是校验后的 IP，不是域名
    assert len(socks_requests) == 1
    assert socks_requests[0][3] in (0x01, 0x04)  # ATYP: IPv4 / IPv6
