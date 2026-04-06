"""API 请求速率限制器（内存滑动窗口）"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """Per-IP 滑动窗口速率限制器。

    Parameters
    ----------
    max_requests : 窗口内最大请求数
    window_seconds : 窗口长度（秒）
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        timestamps = self._requests[key]
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)
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


# 全局限流器实例
_search_limiter = InMemoryRateLimiter(max_requests=60, window_seconds=60)


def rate_limit_search(request: Request) -> None:
    """搜索端点速率限制依赖。"""
    client_ip = request.client.host if request.client else "unknown"
    _search_limiter.check(client_ip)
