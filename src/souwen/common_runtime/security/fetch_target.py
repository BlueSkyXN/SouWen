"""Resolve untrusted HTTP(S) URLs to validated, IP-pinned fetch targets."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse


_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "localhost4",
        "localhost6",
    }
)

_DNS_SSRF_BLOCKED_NETS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.168.0.0/16",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
        "2001:db8::/32",
    )
)
_DIRECT_SSRF_BLOCKED_NETS = _DNS_SSRF_BLOCKED_NETS + (ipaddress.ip_network("198.18.0.0/15"),)

_IPV4_EMBEDDING_NETS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "::/96",
        "::ffff:0:0/96",
        "64:ff9b::/96",
    )
)

_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
_IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True, slots=True)
class ResolvedFetchTarget:
    """A validated URL pinned to one already-checked public IP address."""

    original_url: str
    connect_url: str
    host_header: str
    sni_hostname: str | None


def _embedded_ipv4_address(addr: _IPAddress) -> ipaddress.IPv4Address | None:
    """Return IPv4 embedded in an IPv6 address form, when one is present."""
    if not isinstance(addr, ipaddress.IPv6Address):
        return None

    if addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    if addr.sixtofour is not None:
        return addr.sixtofour
    if addr.teredo is not None:
        return addr.teredo[1]
    if any(addr in net for net in _IPV4_EMBEDDING_NETS):
        return ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    return None


def _is_ssrf_blocked_address(
    addr: _IPAddress,
    blocked_nets: tuple[_IPNetwork, ...],
) -> bool:
    """Check an address and any embedded IPv4 address against SSRF block nets."""
    candidates = [addr]
    embedded = _embedded_ipv4_address(addr)
    if embedded is not None:
        candidates.append(embedded)

    return any(
        candidate.version == net.version and candidate in net
        for candidate in candidates
        for net in blocked_nets
    )


def _parse_legacy_ipv4_literal(hostname: str) -> ipaddress.IPv4Address | None:
    """Parse legacy IPv4 numeric forms accepted by some resolvers."""
    parts = hostname.split(".")
    if not 1 <= len(parts) <= 4 or any(part == "" for part in parts):
        return None

    values: list[int] = []
    for part in parts:
        lower = part.lower()
        if lower.startswith("0x"):
            digits = lower[2:]
            if not digits or any(ch not in "0123456789abcdef" for ch in digits):
                return None
            value = int(digits, 16)
        elif lower.isdigit():
            if len(lower) > 1 and lower.startswith("0"):
                if any(ch not in "01234567" for ch in lower):
                    return None
                value = int(lower, 8)
            else:
                value = int(lower, 10)
        else:
            return None
        values.append(value)

    if len(values) == 1:
        if values[0] > 0xFFFFFFFF:
            return None
        packed = values[0]
    elif len(values) == 2:
        if values[0] > 0xFF or values[1] > 0xFFFFFF:
            return None
        packed = (values[0] << 24) | values[1]
    elif len(values) == 3:
        if values[0] > 0xFF or values[1] > 0xFF or values[2] > 0xFFFF:
            return None
        packed = (values[0] << 24) | (values[1] << 16) | values[2]
    else:
        if any(value > 0xFF for value in values):
            return None
        packed = (values[0] << 24) | (values[1] << 16) | (values[2] << 8) | values[3]
    return ipaddress.IPv4Address(packed)


def _is_legacy_ipv4_numeric_hostname(hostname: str) -> bool:
    """Return whether a host looks like a non-standard IPv4 numeric form."""
    parts = hostname.split(".")
    if not 1 <= len(parts) <= 4 or any(part == "" for part in parts):
        return False

    for part in parts:
        lower = part.lower()
        if lower.startswith("0x"):
            digits = lower[2:]
            if not digits or any(ch not in "0123456789abcdef" for ch in digits):
                return False
            continue
        if not lower.isdigit():
            return False
    return True


def _format_connect_host(addr: _IPAddress) -> str:
    text = str(addr)
    return f"[{text}]" if addr.version == 6 else text


def _format_original_host(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    return f"{host}:{port}" if port is not None else host


def resolve_fetch_target(url: str) -> tuple[ResolvedFetchTarget | None, str]:
    """Validate a URL and bind it to a checked public IP to prevent DNS rebinding.

    The resolver intentionally preserves the current synchronous ``socket.getaddrinfo`` contract.
    It has no timeout or cooperative-cancellation parameter; callers own any outer budget.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return None, "URL 解析失败"

    if parsed.scheme not in ("http", "https"):
        return None, f"不允许的协议: {parsed.scheme}"
    if parsed.username or parsed.password:
        return None, "URL 不允许包含用户信息"

    hostname = parsed.hostname
    if not hostname:
        return None, "缺少主机名"

    try:
        port = parsed.port
    except ValueError:
        return None, "端口号无效"

    hostname_for_ip = hostname.split("%", 1)[0]
    try:
        literal_addr = ipaddress.ip_address(hostname_for_ip)
    except ValueError:
        literal_addr = None
    if literal_addr is None:
        try:
            transport_hostname = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError:
            return None, f"主机名无效: {hostname}"
    else:
        transport_hostname = hostname

    hostname_key = transport_hostname.rstrip(".").lower()
    if hostname_key in _BLOCKED_HOSTNAMES:
        return None, f"目标主机名为本地主机: {hostname}"

    if literal_addr is not None:
        if _is_ssrf_blocked_address(literal_addr, _DIRECT_SSRF_BLOCKED_NETS):
            return None, f"目标地址为内部/私有 IP: {hostname}"
        connect_addr = literal_addr
    else:
        if _is_legacy_ipv4_numeric_hostname(hostname_key):
            legacy_ipv4_addr = _parse_legacy_ipv4_literal(hostname_key)
            resolved_suffix = (
                f" (解析为 {legacy_ipv4_addr})" if legacy_ipv4_addr is not None else ""
            )
            return None, f"非规范 IPv4 数字写法: {hostname}{resolved_suffix}"

        try:
            infos = socket.getaddrinfo(
                transport_hostname,
                None,
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
            )
        except (socket.gaierror, OSError):
            return None, f"DNS 解析失败: {hostname}"

        resolved: list[_IPAddress] = []
        for info in infos:
            try:
                addr_str = info[4][0].split("%", 1)[0]
            except (AttributeError, IndexError, TypeError):
                return None, "DNS 返回无效地址"
            try:
                addr = ipaddress.ip_address(addr_str)
            except ValueError:
                return None, f"DNS 返回无效地址: {addr_str}"
            if _is_ssrf_blocked_address(addr, _DNS_SSRF_BLOCKED_NETS):
                return None, f"目标地址为内部/私有 IP: {addr_str}"
            if addr not in resolved:
                resolved.append(addr)

        if not resolved:
            return None, f"DNS 未返回可用地址: {hostname}"
        connect_addr = next((addr for addr in resolved if addr.version == 4), resolved[0])

    connect_host = _format_connect_host(connect_addr)
    connect_netloc = f"{connect_host}:{port}" if port is not None else connect_host
    connect_url = urlunparse(parsed._replace(netloc=connect_netloc))
    return (
        ResolvedFetchTarget(
            original_url=url,
            connect_url=connect_url,
            host_header=_format_original_host(transport_hostname, port),
            sni_hostname=(
                transport_hostname if parsed.scheme == "https" and literal_addr is None else None
            ),
        ),
        "",
    )


async def resolve_fetch_target_async(url: str) -> tuple[ResolvedFetchTarget | None, str]:
    """Resolve a fetch target without blocking the caller's event loop.

    Cancelling the awaiting task does not terminate an already-running system DNS call in the
    executor thread. The synchronous resolver remains the single source of validation semantics.
    """
    return await asyncio.to_thread(resolve_fetch_target, url)


def validate_fetch_url(url: str) -> tuple[bool, str]:
    """Return whether a URL resolves only to allowed public targets."""
    target, reason = resolve_fetch_target(url)
    return target is not None, reason
