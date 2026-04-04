"""通用异步限流器

支持两种算法：
- TokenBucketLimiter: 令牌桶（固定速率限制，如 PatentsView 45次/分钟）
- SlidingWindowLimiter: 滑动窗口（动态限流，如 The Lens 响应头限流）
"""

from __future__ import annotations

import asyncio
import time
from collections import deque


class TokenBucketLimiter:
    """令牌桶限流器
    
    适用于固定速率限制的数据源。
    
    Args:
        rate: 每秒允许的请求数
        burst: 突发容量（令牌桶大小）
    """

    def __init__(self, rate: float, burst: int | None = None):
        self.rate = rate
        self.burst = burst or max(1, int(rate))
        self._tokens = float(self.burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """获取一个令牌，如果桶空则等待"""
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                # 计算需要等待多久才能拿到一个令牌
                wait_time = (1 - self._tokens) / self.rate
                await asyncio.sleep(wait_time)
                self._refill()

    def _refill(self) -> None:
        """补充令牌"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        self._last_refill = now


class SlidingWindowLimiter:
    """滑动窗口限流器
    
    适用于动态限流（从响应头获取剩余配额）。
    
    Args:
        max_requests: 窗口内最大请求数
        window_seconds: 窗口时间（秒）
    """

    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._retry_until: float = 0  # retry_after 暂停恢复时间点
        self._original_max_requests: int = max_requests  # 暂停前的原始限制

    async def acquire(self) -> None:
        """获取许可，如果窗口已满则等待"""
        async with self._lock:
            # 如果被 retry_after 暂停，等待恢复
            if self._retry_until > 0:
                wait = self._retry_until - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._retry_until = 0
                # 恢复原始限制
                if self._original_max_requests > 0:
                    self.max_requests = self._original_max_requests

            while True:
                now = time.monotonic()
                # 清理过期的时间戳
                cutoff = now - self.window_seconds
                while self._timestamps and self._timestamps[0] < cutoff:
                    self._timestamps.popleft()

                if self.max_requests > 0 and len(self._timestamps) < self.max_requests:
                    self._timestamps.append(now)
                    return

                # 等待最早的请求过期
                if self._timestamps:
                    oldest = self._timestamps[0]
                    wait_time = oldest + self.window_seconds - now + 0.01
                else:
                    wait_time = 1.0  # 安全兜底
                await asyncio.sleep(max(0.01, wait_time))

    def update_from_headers(
        self,
        remaining: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """从响应头更新限流参数（用于 The Lens 等动态限流数据源）"""
        if remaining is not None and remaining <= 0 and retry_after:
            # 暂停直到限流重置，记录恢复时间
            self._original_max_requests = self.max_requests
            self._retry_until = time.monotonic() + retry_after
        elif remaining is not None:
            # 动态调整窗口大小
            current_used = len(self._timestamps)
            if current_used + remaining > 0:
                self.max_requests = current_used + remaining
