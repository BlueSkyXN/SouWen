"""Transient loopback proxy that pins all browser egress to validated IPs (SPEC 10).

Browser Worker 并入主进程后，本模块是其 network_proxy 的等价实现：每个浏览器
请求经回环代理转发，代理对每个 origin 重新执行 SSRF 校验，并用校验后的 IP
直连，杜绝校验与连接之间 DNS 解析不一致带来的重绑定风险。

配置了上游代理（WARP / 用户代理）时，代理链路为 browser → 本回环代理 →
上游代理 → 校验 IP：上游只拿到 IP 字面量，仍不参与域名解析，pinning 与
代理同时成立（SPEC 5.1）。
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Awaitable, Callable
from urllib.parse import urlparse

from souwen.common_runtime.security import ResolvedFetchTarget, resolve_fetch_target_async

from souwen.common_runtime.provider_support.browser_fetch import BrowserAcquisitionError


ResolveTarget = Callable[[str], Awaitable[tuple[ResolvedFetchTarget | None, str]]]
_MAX_HEADER_BYTES = 64 * 1024
_MAX_PROXY_CONNECTIONS = 32
_SOCKS5_TIMEOUT_SECONDS = 10.0
_SOCKS5_REPLY_LEN = 10


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BrowserAcquisitionError("policy_blocked")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise BrowserAcquisitionError("policy_blocked") from None
    return parsed.scheme, parsed.hostname.lower().rstrip("."), port


def _pinned_address(target: ResolvedFetchTarget) -> str:
    hostname = urlparse(target.connect_url).hostname
    if not hostname:
        raise BrowserAcquisitionError("policy_blocked")
    return hostname


def _parse_authority(value: str) -> tuple[str, int]:
    parsed = urlparse(f"//{value}")
    if not parsed.hostname:
        raise BrowserAcquisitionError("policy_blocked")
    try:
        port = parsed.port
    except ValueError:
        raise BrowserAcquisitionError("policy_blocked") from None
    if port is None:
        raise BrowserAcquisitionError("policy_blocked")
    return parsed.hostname.lower().rstrip("."), port


def _ipv6_literal(address: str) -> bool:
    return ":" in address and not address.startswith("[")


def _upstream_parts(upstream_proxy: str) -> tuple[str, str, int]:
    """Split an upstream proxy URL into (scheme, host, port)."""

    parsed = urlparse(upstream_proxy)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"socks5", "socks5h", "http", "https"} or not parsed.hostname:
        raise BrowserAcquisitionError("policy_blocked")
    try:
        port = parsed.port
    except ValueError:
        raise BrowserAcquisitionError("policy_blocked") from None
    if port is None:
        port = 1080 if scheme.startswith("socks5") else (443 if scheme == "https" else 80)
    return scheme, parsed.hostname, port


async def _connect_via_socks5(
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
    pinned_address: str,
    port: int,
) -> None:
    """SOCKS5 CONNECT (no auth, RFC 1928) to the validated IP literal."""

    # 地址只可能是校验后的 IP 字面量；不再给上游任何域名。
    import ipaddress

    try:
        address = ipaddress.ip_address(pinned_address)
    except ValueError:
        raise BrowserAcquisitionError("policy_blocked") from None
    if address.version == 4:
        address_bytes = bytes((0x01,)) + address.packed
    else:
        address_bytes = bytes((0x04,)) + address.packed
    # greeting: VER=5, 1 method, NO AUTHENTICATION REQUIRED
    upstream_writer.write(b"\x05\x01\x00")
    await upstream_writer.drain()
    greeting = await asyncio.wait_for(upstream_reader.readexactly(2), _SOCKS5_TIMEOUT_SECONDS)
    if greeting[0] != 0x05 or greeting[1] != 0x00:
        raise BrowserAcquisitionError("worker_unavailable")
    # request: VER=5 CMD=CONNECT RSV=0 ATYP + addr + port
    request = b"\x05\x01\x00" + address_bytes + port.to_bytes(2, "big")
    upstream_writer.write(request)
    await upstream_writer.drain()
    reply = await asyncio.wait_for(
        upstream_reader.readexactly(_SOCKS5_REPLY_LEN), _SOCKS5_TIMEOUT_SECONDS
    )
    # reply: VER REP RSV ATYP BND.ADDR BND.PORT — 固定按 IPv4 长度读取，
    # 域名/IPv6 的 BND.ADDR 均为占位，长度差异只影响尾部字节。
    if reply[0] != 0x05 or reply[1] != 0x00:
        raise BrowserAcquisitionError("worker_unavailable")


class PinnedLoopbackProxy:
    """Policy proxy; every browser origin is revalidated and connected by pinned IP."""

    def __init__(
        self,
        *,
        target_url: str,
        resolver: ResolveTarget = resolve_fetch_target_async,
        upstream_proxy: str | None = None,
    ) -> None:
        self._allowed_origins = {_origin(target_url)}
        self._resolver = resolver
        self._upstream_proxy = upstream_proxy
        self._server: asyncio.AbstractServer | None = None
        self._handlers: set[asyncio.Task[None]] = set()
        self._active_connections = 0
        self._connection_lock = asyncio.Lock()
        self._port: int | None = None

    def allow_url(self, url: str) -> None:
        """Permit an origin only after the Playwright route policy has validated its URL."""
        self._allowed_origins.add(_origin(url))

    @property
    def url(self) -> str:
        if self._port is None:
            raise RuntimeError("proxy has not started")
        return f"http://127.0.0.1:{self._port}"

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(
            self._accept,
            "127.0.0.1",
            0,
            limit=_MAX_HEADER_BYTES,
            backlog=_MAX_PROXY_CONNECTIONS,
        )
        sockets = self._server.sockets or ()
        if len(sockets) != 1:
            await self.close()
            raise BrowserAcquisitionError("worker_unavailable", retryable=True)
        self._port = int(sockets[0].getsockname()[1])

    async def _open_upstream(self, pinned_address: str, port: int):
        """连接校验后的 IP；有上游代理时经上游建连，仍不交给上游解析域名。"""

        if self._upstream_proxy is None:
            return await asyncio.open_connection(
                pinned_address if not _ipv6_literal(pinned_address) else f"[{pinned_address}]",
                port,
            )
        scheme, upstream_host, upstream_port = _upstream_parts(self._upstream_proxy)
        reader, writer = await asyncio.open_connection(upstream_host, upstream_port)
        if scheme.startswith("socks5"):
            await _connect_via_socks5(reader, writer, pinned_address, port)
            return reader, writer
        if scheme in {"http", "https"}:
            # HTTP 上游代理：把 pinning 代理变成链式绝对 URI 代理。
            # Chromium 的 CONNECT 隧道不经过本分支（见 _handle）。
            raise BrowserAcquisitionError("policy_blocked")
        raise BrowserAcquisitionError("policy_blocked")

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._handlers.add(task)
        async with self._connection_lock:
            if self._active_connections >= _MAX_PROXY_CONNECTIONS:
                writer.write(b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n\r\n")
                await writer.drain()
                writer.close()
                if task is not None:
                    self._handlers.discard(task)
                return
            self._active_connections += 1
        try:
            await self._handle(reader, writer)
        except asyncio.CancelledError:
            raise
        except Exception:
            with suppress(Exception):
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
                await writer.drain()
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
            if task is not None:
                self._handlers.discard(task)
            async with self._connection_lock:
                self._active_connections -= 1

    async def _read_head(self, reader: asyncio.StreamReader) -> tuple[bytes, bytes]:
        buffer = bytearray()
        while b"\r\n\r\n" not in buffer:
            chunk = await reader.read(4096)
            if not chunk:
                raise BrowserAcquisitionError("worker_unavailable")
            buffer.extend(chunk)
            if len(buffer) > _MAX_HEADER_BYTES:
                raise BrowserAcquisitionError("policy_blocked")
        head, remainder = bytes(buffer).split(b"\r\n\r\n", 1)
        return head, remainder

    async def _validate(self, scheme: str, hostname: str, port: int) -> ResolvedFetchTarget:
        if (scheme, hostname, port) not in self._allowed_origins:
            raise BrowserAcquisitionError("policy_blocked")
        rendered_host = f"[{hostname}]" if ":" in hostname else hostname
        candidate_url = f"{scheme}://{rendered_host}:{port}/"
        target, _reason = await self._resolver(candidate_url)
        if target is None:
            raise BrowserAcquisitionError("policy_blocked")
        _pinned_address(target)
        return target

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head, remainder = await self._read_head(reader)
        lines = head.split(b"\r\n")
        try:
            method_bytes, target_bytes, version = lines[0].split(b" ", 2)
            method = method_bytes.decode("ascii").upper()
            request_target = target_bytes.decode("ascii")
        except (UnicodeDecodeError, ValueError):
            raise BrowserAcquisitionError("policy_blocked") from None

        if method == "CONNECT":
            hostname, port = _parse_authority(request_target)
            target = await self._validate("https", hostname, port)
            upstream_reader, upstream_writer = await self._open_upstream(
                _pinned_address(target), port
            )
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            if remainder:
                upstream_writer.write(remainder)
                await upstream_writer.drain()
            await self._tunnel(reader, writer, upstream_reader, upstream_writer)
            return

        if method not in {"GET", "HEAD"}:
            raise BrowserAcquisitionError("policy_blocked")
        parsed = urlparse(request_target)
        if parsed.scheme != "http" or not parsed.hostname:
            raise BrowserAcquisitionError("policy_blocked")
        try:
            port = parsed.port or 80
        except ValueError:
            raise BrowserAcquisitionError("policy_blocked") from None
        hostname = parsed.hostname.lower().rstrip(".")
        target = await self._validate("http", hostname, port)
        if remainder:
            raise BrowserAcquisitionError("policy_blocked")

        upstream_reader, upstream_writer = await self._open_upstream(_pinned_address(target), port)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        filtered_headers = [
            line
            for line in lines[1:]
            if not line.lower().startswith((b"proxy-authorization:", b"connection:"))
        ]
        rewritten = b"\r\n".join(
            [b" ".join((method_bytes, path.encode("ascii"), version)), *filtered_headers]
        )
        upstream_writer.write(rewritten + b"\r\nConnection: close\r\n\r\n")
        await upstream_writer.drain()
        try:
            while chunk := await upstream_reader.read(65536):
                writer.write(chunk)
                await writer.drain()
        finally:
            upstream_writer.close()
            with suppress(Exception):
                await upstream_writer.wait_closed()

    async def _tunnel(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            while chunk := await reader.read(65536):
                writer.write(chunk)
                await writer.drain()

        client_to_upstream = asyncio.create_task(pump(client_reader, upstream_writer))
        upstream_to_client = asyncio.create_task(pump(upstream_reader, client_writer))
        try:
            done, pending = await asyncio.wait(
                {client_to_upstream, upstream_to_client},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
        finally:
            upstream_writer.close()
            with suppress(Exception):
                await upstream_writer.wait_closed()

    async def close(self) -> None:
        server = self._server
        self._server = None
        self._port = None
        if server is not None:
            server.close()
            await server.wait_closed()
        handlers = [task for task in self._handlers if task is not asyncio.current_task()]
        for task in handlers:
            task.cancel()
        if handlers:
            await asyncio.gather(*handlers, return_exceptions=True)
        self._handlers.clear()


__all__ = ["PinnedLoopbackProxy"]
