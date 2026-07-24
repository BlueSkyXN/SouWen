"""Common Runtime SSRF target resolver parity and dependency tests."""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
import socket
import threading
from typing import Any
from unittest.mock import AsyncMock

import pytest

from souwen.common_runtime.security import (
    ResolvedFetchTarget,
    resolve_fetch_target,
    resolve_fetch_target_async,
    validate_fetch_url,
)
from souwen.common_runtime.security import fetch_target as canonical_fetch_target
from souwen.core.scraper import base as scraper_base
from souwen.web import builtin as builtin_module
from souwen.web import fetch as legacy_fetch


def _addrinfo(address: str, port: int = 443) -> tuple[Any, ...]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))


def test_legacy_fetch_path_reexports_canonical_ssrf_interface() -> None:
    assert legacy_fetch.ResolvedFetchTarget is ResolvedFetchTarget
    assert legacy_fetch.resolve_fetch_target is resolve_fetch_target
    assert legacy_fetch.validate_fetch_url is validate_fetch_url


def test_base_scraper_uses_canonical_ssrf_interface() -> None:
    assert scraper_base.ResolvedFetchTarget is ResolvedFetchTarget
    assert scraper_base.resolve_fetch_target is resolve_fetch_target
    assert scraper_base.resolve_fetch_target_async is resolve_fetch_target_async
    assert builtin_module.resolve_fetch_target_async is resolve_fetch_target_async


def test_canonical_fetch_target_has_only_stdlib_dependencies() -> None:
    path = Path(canonical_fetch_target.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imported_roots = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        (node.module or "").split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )

    assert imported_roots == {
        "__future__",
        "asyncio",
        "dataclasses",
        "ipaddress",
        "socket",
        "urllib",
    }
    assert "return await asyncio.to_thread(resolve_fetch_target, url)" in source
    assert inspect.iscoroutinefunction(resolve_fetch_target_async) is True
    assert list(inspect.signature(resolve_fetch_target_async).parameters) == ["url"]


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("ftp://example.com/file", "不允许的协议: ftp"),
        ("http://user:pass@example.com/", "URL 不允许包含用户信息"),
        ("http:///path", "缺少主机名"),
        ("http://example.com:invalid/", "端口号无效"),
        ("http://localhost./", "目标主机名为本地主机: localhost."),
        ("http://127.0.0.1/", "目标地址为内部/私有 IP: 127.0.0.1"),
        ("https://198.18.1.47/", "目标地址为内部/私有 IP: 198.18.1.47"),
        ("http://2130706433/", "非规范 IPv4 数字写法: 2130706433 (解析为 127.0.0.1)"),
    ],
)
def test_ssrf_rejection_reason_contract_is_preserved(url: str, reason: str) -> None:
    assert resolve_fetch_target(url) == (None, reason)
    assert validate_fetch_url(url) == (False, reason)


def test_resolver_preserves_synchronous_dns_and_ipv4_preference(monkeypatch) -> None:
    calls: list[tuple[int, str, int | None, int, int]] = []

    def getaddrinfo(
        host: str,
        port: int | None,
        family: int,
        socktype: int,
    ) -> list[tuple[Any, ...]]:
        calls.append((threading.get_ident(), host, port, family, socktype))
        return [
            _addrinfo("2606:4700:4700::1111"),
            _addrinfo("1.1.1.1"),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    target, reason = resolve_fetch_target("https://example.com:8443/path?q=1")

    assert inspect.iscoroutinefunction(resolve_fetch_target) is False
    assert list(inspect.signature(resolve_fetch_target).parameters) == ["url"]
    assert calls == [
        (
            threading.get_ident(),
            "example.com",
            None,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    ]
    assert reason == ""
    assert target == ResolvedFetchTarget(
        original_url="https://example.com:8443/path?q=1",
        connect_url="https://1.1.1.1:8443/path?q=1",
        host_header="example.com:8443",
        sni_hostname="example.com",
    )


@pytest.mark.asyncio
async def test_async_resolver_offloads_dns_and_preserves_exact_target(monkeypatch) -> None:
    caller_thread = threading.get_ident()
    resolver_threads: list[int] = []

    def getaddrinfo(*_args: object, **_kwargs: object) -> list[tuple[Any, ...]]:
        resolver_threads.append(threading.get_ident())
        return [
            _addrinfo("2606:4700:4700::1111"),
            _addrinfo("1.1.1.1"),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    url = "https://example.com:8443/path?q=1"
    expected = resolve_fetch_target(url)
    actual = await resolve_fetch_target_async(url)

    assert actual == expected
    assert resolver_threads[0] == caller_thread
    assert resolver_threads[1] != caller_thread


@pytest.mark.asyncio
async def test_async_wrapper_reads_canonical_sync_resolver_at_call_time(monkeypatch) -> None:
    expected = ResolvedFetchTarget(
        original_url="https://fixture.example/resource",
        connect_url="https://1.1.1.1/resource",
        host_header="fixture.example",
        sni_hostname="fixture.example",
    )
    monkeypatch.setattr(
        canonical_fetch_target,
        "resolve_fetch_target",
        lambda _url: (expected, ""),
    )

    assert await resolve_fetch_target_async("https://fixture.example/resource") == (expected, "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "dns_result"),
    [
        (
            "https://mixed.example/resource",
            [_addrinfo("1.1.1.1"), _addrinfo("169.254.169.254")],
        ),
        ("https://fake-ip.example/resource", [_addrinfo("198.18.1.47")]),
        ("https://bücher.example:8443/path", [_addrinfo("1.1.1.1")]),
        ("https://ipv6.example:8443/path", [_addrinfo("2606:4700:4700::1111")]),
        ("https://dns-failure.example/resource", socket.gaierror("fixture DNS failure")),
        (
            "https://malformed.example/resource",
            [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (None, 443))],
        ),
        ("http://2130706433/", []),
        ("https://198.18.1.47/", []),
    ],
)
async def test_async_resolver_matches_sync_security_results(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    dns_result: object,
) -> None:
    def getaddrinfo(*_args: object, **_kwargs: object) -> list[tuple[Any, ...]]:
        if isinstance(dns_result, BaseException):
            raise dns_result
        return dns_result  # type: ignore[return-value]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    expected = resolve_fetch_target(url)
    actual = await resolve_fetch_target_async(url)

    assert actual == expected


def _blocking_dns_events(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[threading.Event, threading.Event, threading.Event]:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def getaddrinfo(*_args: object, **_kwargs: object) -> list[tuple[Any, ...]]:
        started.set()
        if not release.wait(timeout=5):
            raise RuntimeError("test DNS release timed out")
        finished.set()
        return [_addrinfo("1.1.1.1")]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return started, release, finished


async def _wait_for_thread_event(event: threading.Event) -> None:
    assert await asyncio.to_thread(event.wait, 1)


@pytest.mark.asyncio
async def test_async_resolver_cancellation_releases_waiter_but_not_running_dns_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, release, finished = _blocking_dns_events(monkeypatch)
    task = asyncio.create_task(resolve_fetch_target_async("https://example.com/resource"))
    worker_finished = False
    try:
        await _wait_for_thread_event(started)

        ticked = False

        async def tick() -> None:
            nonlocal ticked
            await asyncio.sleep(0)
            ticked = True

        await asyncio.wait_for(tick(), timeout=0.2)
        assert ticked is True
        assert task.done() is False

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set() is False
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass
        release.set()
        worker_finished = await asyncio.to_thread(finished.wait, 1)
    assert worker_finished is True


@pytest.mark.asyncio
async def test_outer_timeout_stops_waiting_but_does_not_claim_hard_dns_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, release, finished = _blocking_dns_events(monkeypatch)
    task = asyncio.create_task(
        asyncio.wait_for(
            resolve_fetch_target_async("https://example.com/resource"),
            timeout=0.05,
        )
    )
    worker_finished = False
    try:
        await _wait_for_thread_event(started)

        with pytest.raises(asyncio.TimeoutError):
            await task
        assert finished.is_set() is False
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass
        release.set()
        worker_finished = await asyncio.to_thread(finished.wait, 1)
    assert worker_finished is True


@pytest.mark.asyncio
@pytest.mark.parametrize("consumer", ["base_scraper", "builtin"])
async def test_cancelled_async_dns_consumer_never_starts_transport_after_worker_finishes(
    monkeypatch: pytest.MonkeyPatch,
    consumer: str,
) -> None:
    started, release, finished = _blocking_dns_events(monkeypatch)
    request = AsyncMock()

    if consumer == "base_scraper":
        instance = object.__new__(scraper_base.BaseScraper)
        instance._fetch = request
        coroutine = instance._fetch_with_safe_redirects("https://example.com/resource")
    else:
        instance = object.__new__(builtin_module.BuiltinFetcherClient)
        instance._check_robots = AsyncMock(return_value=(True, ""))
        instance._fetch = request
        coroutine = instance._fetch_impl("https://example.com/resource")

    task = asyncio.create_task(coroutine)
    worker_finished = False
    try:
        await _wait_for_thread_event(started)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass
        release.set()
        worker_finished = await asyncio.to_thread(finished.wait, 1)
    assert worker_finished is True
    await asyncio.sleep(0)
    request.assert_not_awaited()


def test_resolver_still_fails_closed_on_mixed_dns_answers(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            _addrinfo("1.1.1.1"),
            _addrinfo("169.254.169.254"),
        ],
    )

    assert resolve_fetch_target("https://example.com/resource") == (
        None,
        "目标地址为内部/私有 IP: 169.254.169.254",
    )


def test_legacy_validate_monkeypatch_still_controls_fetch_helpers(monkeypatch) -> None:
    monkeypatch.setattr(
        legacy_fetch,
        "validate_fetch_url",
        lambda _url: (False, "patched legacy guard"),
    )

    result = legacy_fetch.ssrf_blocked_fetch_result("https://example.com", "fixture")

    assert result is not None
    assert result.error == "SSRF 校验失败: patched legacy guard"
    assert result.raw == {"provider": "fixture", "blocked_by_ssrf": True}
