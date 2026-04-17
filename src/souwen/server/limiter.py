"""API 请求速率限制器（内存滑动窗口）"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections import defaultdict, deque
from typing import Iterable

from fastapi import HTTPException, Request, status

logger = logging.getLogger("souwen.server.limiter")


class InMemoryRateLimiter:
    """Per-IP 滑动窗口速率限制器。

    Parameters
    ----------
    max_requests : 窗口内最大请求数，必须 > 0
    window_seconds : 窗口长度（秒），必须 > 0
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        if max_requests <= 0:
            raise ValueError(f"max_requests 必须 > 0，当前 {max_requests}")
        if window_seconds <= 0:
            raise ValueError(f"window_seconds 必须 > 0，当前 {window_seconds}")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # 用 deque(maxlen=max_requests * 2) 保证内存有界，防止 DoS
        self._requests: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=max_requests * 2)
        )

    def _cleanup(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        timestamps = self._requests[key]
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        if not timestamps:
            self._requests.pop(key, None)

    def check(self, key: str) -> None:
        """检查是否超限，超限则抛出 HTTPException 429。"""
        now = time.monotonic()
        self._cleanup(key, now)
        timestamps = self._requests[key]
        if len(timestamps) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，每 {self.window_seconds} 秒最多 {self.max_requests} 次",
                headers={"Retry-After": str(self.window_seconds)},
            )
        timestamps.append(now)


def _parse_trusted_networks(
    values: Iterable[str],
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """把配置中的代理白名单字符串解析成 ip_network 对象，解析失败的条目会被记录并跳过。"""
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw in values:
        if not isinstance(raw, str):
            continue
        item = raw.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("trusted_proxies 中 %r 不是合法的 IP/CIDR，已忽略", item)
    return networks


def _ip_in_networks(
    ip_str: str,
    networks: Iterable[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def get_client_ip(request: Request) -> str:
    """解析真实客户端 IP。

    规则：只有当直连 peer 属于 ``trusted_proxies`` 中的网段时，才信任
    ``X-Forwarded-For`` 头的最左侧 IP。否则直接使用 TCP 连接对端地址，
    忽略任意用户可伪造的头部。
    """
    peer = request.client.host if request.client else "unknown"

    try:
        from souwen.config import get_config

        trusted_raw = get_config().trusted_proxies or []
    except Exception:  # pragma: no cover - 配置出错时回退到 peer
        logger.debug("读取 trusted_proxies 失败，忽略 XFF", exc_info=True)
        return peer

    if not trusted_raw:
        return peer

    networks = _parse_trusted_networks(trusted_raw)
    if not networks or not _ip_in_networks(peer, networks):
        return peer

    xff = request.headers.get("x-forwarded-for", "")
    for part in xff.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        return candidate
    return peer


# 全局限流器实例
_search_limiter = InMemoryRateLimiter(max_requests=60, window_seconds=60)


def rate_limit_search(request: Request) -> None:
    """搜索端点速率限制依赖。"""
    _search_limiter.check(get_client_ip(request))
