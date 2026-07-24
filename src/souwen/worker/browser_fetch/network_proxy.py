"""Transient loopback proxy that pins all browser egress to one validated origin."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Awaitable, Callable
from urllib.parse import urlparse

from souwen.common_runtime.security import ResolvedFetchTarget, resolve_fetch_target_async

from .executor import BrowserExecutionError


ResolveTarget = Callable[[str], Awaitable[tuple[ResolvedFetchTarget | None, str]]]
_MAX_HEADER_BYTES = 64 * 1024
_MAX_PROXY_CONNECTIONS = 32


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BrowserExecutionError("policy_blocked")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise BrowserExecutionError("policy_blocked") from None
    return parsed.scheme, parsed.hostname.lower().rstrip("."), port


def _pinned_address(target: ResolvedFetchTarget) -> str:
    hostname = urlparse(target.connect_url).hostname
    if not hostname:
        raise BrowserExecutionError("policy_blocked")
    return hostname


def _parse_authority(value: str) -> tuple[str, int]:
    parsed = urlparse(f"//{value}")
    if not parsed.hostname:
        raise BrowserExecutionError("policy_blocked")
    try:
        port = parsed.port
    except ValueError:
        raise BrowserExecutionError("policy_blocked") from None
    if port is None:
        raise BrowserExecutionError("policy_blocked")
    return parsed.hostname.lower().rstrip("."), port


class PinnedLoopbackProxy:
    """Policy proxy; every browser origin is revalidated and connected by pinned IP."""

    def __init__(
        self,
        *,
        target_url: str,
        resolver: ResolveTarget = resolve_fetch_target_async,
    ) -> None:
        self._allowed_origins = {_origin(target_url)}
        self._resolver = resolver
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
            raise BrowserExecutionError("worker_unavailable", retryable=True)
        self._port = int(sockets[0].getsockname()[1])

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
                raise BrowserExecutionError("worker_unavailable")
            buffer.extend(chunk)
            if len(buffer) > _MAX_HEADER_BYTES:
                raise BrowserExecutionError("policy_blocked")
        head, remainder = bytes(buffer).split(b"\r\n\r\n", 1)
        return head, remainder

    async def _validate(self, scheme: str, hostname: str, port: int) -> ResolvedFetchTarget:
        if (scheme, hostname, port) not in self._allowed_origins:
            raise BrowserExecutionError("policy_blocked")
        rendered_host = f"[{hostname}]" if ":" in hostname else hostname
        candidate_url = f"{scheme}://{rendered_host}:{port}/"
        target, _reason = await self._resolver(candidate_url)
        if target is None:
            raise BrowserExecutionError("policy_blocked")
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
            raise BrowserExecutionError("policy_blocked") from None

        if method == "CONNECT":
            hostname, port = _parse_authority(request_target)
            target = await self._validate("https", hostname, port)
            upstream_reader, upstream_writer = await asyncio.open_connection(
                _pinned_address(target),
                port,
            )
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            if remainder:
                upstream_writer.write(remainder)
                await upstream_writer.drain()
            await self._tunnel(reader, writer, upstream_reader, upstream_writer)
            return

        if method not in {"GET", "HEAD"}:
            raise BrowserExecutionError("policy_blocked")
        parsed = urlparse(request_target)
        if parsed.scheme != "http" or not parsed.hostname:
            raise BrowserExecutionError("policy_blocked")
        try:
            port = parsed.port or 80
        except ValueError:
            raise BrowserExecutionError("policy_blocked") from None
        hostname = parsed.hostname.lower().rstrip(".")
        target = await self._validate("http", hostname, port)
        if remainder:
            raise BrowserExecutionError("policy_blocked")

        upstream_reader, upstream_writer = await asyncio.open_connection(
            _pinned_address(target),
            port,
        )
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
