"""Local TCP proof that browser egress uses the validated IP and exact origin."""

from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

from souwen.common_runtime.security import ResolvedFetchTarget
from souwen.worker.browser_fetch.network_proxy import PinnedLoopbackProxy


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
