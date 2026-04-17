"""API 请求速率限制器 — 基于内存的滑动窗口算法

文件用途：
    提供按客户端 IP 的速率限制和代理信任配置。防止 DoS 攻击和滥用。

主要类/函数：
    InMemoryRateLimiter(max_requests: int, window_seconds: int)
        - 功能：Per-IP 滑动窗口速率限制器
        - 参数：
            max_requests：窗口内最大请求数（必须 > 0）
            window_seconds：窗口长度（秒，必须 > 0）
        - 关键属性：
            _requests：dict[IP, deque]，用 deque(maxlen=max_requests*2) 存储时间戳
            maxlen 保证内存有界，防止 DoS 攻击导致内存爆炸
        - 主要方法：
            check(key: str) -> None：检查是否超限，超限时抛出 429 HTTPException
            _cleanup(key: str, now: float)：移除超出窗口的时间戳

    _parse_trusted_networks(values: Iterable[str]) -> list[ipaddress networks]
        - 功能：解析配置中的代理白名单（CIDR 格式）
        - 输入：字符串列表，如 ["10.0.0.0/8", "192.168.0.0/16"]
        - 输出：ipaddress 网段对象列表，解析失败的条目被记录并跳过

    _ip_in_networks(ip_str: str, networks: Iterable) -> bool
        - 功能：检查 IP 是否属于某个信任的网段
        - 输入：IP 字符串、网段列表
        - 返回：True 当 IP 在白名单中

    get_client_ip(request: Request) -> str
        - 功能：解析真实客户端 IP（支持 X-Forwarded-For 头）
        - 规则：
            1. 只有当直连 peer 属于 trusted_proxies 白名单时，才信任 X-Forwarded-For
            2. 否则使用 TCP 连接对端地址，忽略任何用户可伪造的头部
        - 返回：IP 字符串

    rate_limit_search(request: Request) -> None
        - 功能：搜索端点速率限制依赖
        - 调用全局限流器检查，超限时抛出 429

全局实例：
    _search_limiter：Per-IP 搜索限流器，60 请求/分钟（可配置）

模块依赖：
    - fastapi：HTTP 异常和请求对象
    - ipaddress：IP 地址和网段解析
"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections import defaultdict, deque
from typing import Iterable

from fastapi import HTTPException, Request, status

logger = logging.getLogger("souwen.server.limiter")


class InMemoryRateLimiter:
    """Per-IP 滑动窗口速率限制器 — 防 DoS 和滥用

    使用 deque(maxlen) 存储时间戳，确保内存有界（防止 DoS）。
    每次检查时自动清理超出窗口的时间戳。

    Parameters
    ----------
    max_requests : int
        窗口内最大请求数，必须 > 0
    window_seconds : int
        窗口长度（秒），必须 > 0。例如 60 表示 1 分钟内 max_requests 个请求

    Attributes
    ----------
    _requests : dict[str, deque[float]]
        按客户端 IP 存储请求时间戳。deque 的 maxlen 设为 max_requests*2
        确保内存占用有界，即使有大量不同 IP 也不会无限增长
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
        """清理超出时间窗口的时间戳 — 维持滑动窗口的准确性

        移除所有早于 (now - window_seconds) 的时间戳，若队列变空则删除键。

        Args:
            key: 客户端 IP
            now: 当前时间（单调时钟，通常来自 time.monotonic()）
        """
        cutoff = now - self.window_seconds
        timestamps = self._requests[key]
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        if not timestamps:
            self._requests.pop(key, None)

    def check(self, key: str) -> None:
        """检查是否超限，超限则抛出 HTTPException 429

        步骤：
        1. 清理超出窗口的时间戳
        2. 检查窗口内请求数是否达到上限
        3. 若超限，计算 Retry-After 和 X-RateLimit 响应头
        4. 否则记录当前时间戳

        Args:
            key: 客户端 IP 字符串

        Raises:
            HTTPException：429 Too Many Requests，包含 Retry-After 等头信息

        Notes:
            使用 time.monotonic() 而非 time.time()，避免系统时钟调整影响
        """
        now = time.monotonic()
        self._cleanup(key, now)
        timestamps = self._requests[key]
        if len(timestamps) >= self.max_requests:
            # 计算 reset 时间（最早一次请求滑出窗口的绝对时间，秒级 epoch）
            oldest = timestamps[0]
            retry_after = max(1, int(self.window_seconds - (now - oldest)) + 1)
            reset_epoch = int(time.time()) + retry_after
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，每 {self.window_seconds} 秒最多 {self.max_requests} 次",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_epoch),
                },
            )
        timestamps.append(now)


def _parse_trusted_networks(
    values: Iterable[str],
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """解析代理白名单字符串为 ipaddress 网段对象 — 验证代理身份

    接受 CIDR 格式的网段字符串（如 "10.0.0.0/8"）。
    解析失败的条目会被记录为警告并跳过。

    Args:
        values: 字符串迭代器，可包含 CIDR 格式网段

    Returns:
        ipaddress 网段对象列表，可用于 _ip_in_networks 检查
    """
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
    """检查 IP 是否属于某个信任的网段 — 验证代理来源

    Args:
        ip_str: IP 地址字符串（如 "10.0.0.1"）
        networks: ipaddress 网段对象列表

    Returns:
        True 当 IP 在白名单中某个网段内，False 否则（包括 IP 格式错误）
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def get_client_ip(request: Request) -> str:
    """解析真实客户端 IP — 支持代理场景但防止伪造

    规则：
        1. 获取 TCP 直连对端地址（peer）
        2. 检查 peer 是否属于 trusted_proxies 白名单
        3. 若是，从 X-Forwarded-For 头提取最左侧 IP
        4. 否则，直接返回 peer（忽略任何头部）

    这样防止了客户端伪造 X-Forwarded-For 头来欺骗速率限制。

    Args:
        request: FastAPI Request 对象

    Returns:
        客户端 IP 地址字符串，或 "unknown" 当无法确定
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
    """搜索端点速率限制依赖 — FastAPI 依赖注入

    从全局 _search_limiter 检查客户端 IP 的请求频率。
    若超限，自动抛出 429 HTTPException。

    Args:
        request: FastAPI Request 对象

    Raises:
        HTTPException：429 Too Many Requests

    Usage:
        @router.get("/search", dependencies=[Depends(rate_limit_search)])
        async def search(...):
            ...
    """
    _search_limiter.check(get_client_ip(request))
