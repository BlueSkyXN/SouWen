"""通用异步限流器

文件用途：
    提供多种限流算法实现，支持固定速率和动态限流。
    可通过继承 RateLimiterBase 实现自定义限流器（如基于 Redis 的分布式限流）。

限流算法：
    1. TokenBucketLimiter: 令牌桶算法（固定速率限制）
       - 适用于：恒定速率的数据源（如 PatentsView 45 次/分钟）
       - 特点：令牌匀速补充，达到突发请求处理能力
    
    2. SlidingWindowLimiter: 滑动窗口算法（动态限流）
       - 适用于：响应头返回剩余配额的数据源（如 The Lens）
       - 特点：根据实时配额动态调整限流，支持 retry_after 暂停

类清单：
    RateLimiterBase（抽象基类）
        - 功能：限流器接口定义
        - 方法：
          * acquire() → Coroutine — 异步获取一个许可，达到限流阈值时等待
          * update_from_headers(remaining, retry_after) — 从响应头更新限流参数（可选）
    
    TokenBucketLimiter(RateLimiterBase)
        - 功能：令牌桶限流
        - 入参：rate (float) 每秒请求数, burst (int|None) 突发容量（默认 = rate）
        - 关键属性：rate、burst、_tokens、_lock
        - 算法：令牌桶容量为 burst，以 rate 速率补充，每次 acquire() 消耗 1 个令牌
    
    SlidingWindowLimiter(RateLimiterBase)
        - 功能：滑动窗口限流，支持动态调整
        - 入参：max_requests (int) 窗口内最大请求数, window_seconds (float) 窗口时间
        - 关键属性：_timestamps (deque), _retry_until, _original_max_requests
        - 算法：维护时间戳队列，清理过期请求，等待队列腾出空位
        - 特性：支持 update_from_headers() 实时调整配额，支持 retry_after 暂停

模块依赖：
    - abc: 抽象基类定义
    - asyncio: 异步锁和睡眠
    - time: 单调时钟
    - collections.deque: 高效时间戳队列
"""

from __future__ import annotations

import abc
import asyncio
import time
from collections import deque


class RateLimiterBase(abc.ABC):
    """限流器抽象基类

    所有限流器实现必须继承此类并实现 acquire() 方法。
    
    扩展示例 — 基于 Redis 的分布式限流器::

        class RedisRateLimiter(RateLimiterBase):
            def __init__(self, redis_client, key, max_requests, window):
                self._redis = redis_client
                self._key = key
                self._max = max_requests
                self._window = window

            async def acquire(self) -> None:
                # 使用 Redis Lua 脚本实现原子计数 + 过期，
                # 适用于多进程 / 多节点部署场景。
                ...
    """

    @abc.abstractmethod
    async def acquire(self) -> None:
        """获取一个许可，如果达到限流阈值则等待
        
        实现类应在此方法中：
        1. 检查是否可以处理新请求
        2. 若可以，立即返回
        3. 若不可以，计算需要等待的时间并 await asyncio.sleep()
        """

    def update_from_headers(
        self,
        remaining: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """从响应头更新限流参数（默认无操作，子类可选覆盖）
        
        Args:
            remaining: 剩余配额（如 The Lens 的 X-RateLimit-Remaining）
            retry_after: 建议重试等待秒数（如 Retry-After 头）
        
        说明：
            基类提供空实现，子类可覆盖此方法以支持动态限流调整。
        """


class TokenBucketLimiter(RateLimiterBase):
    """令牌桶限流器

    适用于恒定速率限制的数据源。令牌匀速补充到桶中，
    每次 acquire() 消耗 1 个令牌。突发请求可快速消耗累积的令牌。
    
    Args:
        rate: 每秒允许的请求数（令牌补充速率）
        burst: 突发容量，即令牌桶大小；不指定则默认 = rate
    """

    def __init__(self, rate: float, burst: int | None = None):
        """初始化令牌桶限流器
        
        Args:
            rate: 每秒补充的令牌数，必须 > 0
            burst: 令牌桶容量，不指定则默认 max(1, int(rate))
        
        Raises:
            ValueError: rate <= 0 时抛出
        """
        if rate <= 0:
            raise ValueError(f"rate 必须大于 0，收到: {rate}")
        self.rate = rate
        self.burst = burst or max(1, int(rate))
        self._tokens = float(self.burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """获取一个令牌，如果桶空则等待
        
        算法：
        1. 获取锁（并发安全）
        2. 补充令牌（根据时间流逝）
        3. 如果有令牌，消耗 1 个并返回
        4. 否则计算等待时间并 sleep，重复尝试
        """
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
        """补充令牌（根据时间流逝，但不超过桶容量）"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        # 按时间流逝匀速补充令牌，但不超过桶容量（burst）
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        self._last_refill = now


class SlidingWindowLimiter(RateLimiterBase):
    """滑动窗口限流器

    适用于动态限流（从响应头获取剩余配额）。维护时间戳队列，
    清理过期时间戳，支持 update_from_headers() 实时调整限额。
    
    Args:
        max_requests: 窗口内最大请求数
        window_seconds: 窗口时间（秒）
    """

    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        """初始化滑动窗口限流器
        
        Args:
            max_requests: 滑动窗口内允许的最大请求数
            window_seconds: 时间窗口大小（秒），默认 60s
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._retry_until: float = 0  # retry_after 暂停恢复时间点
        self._original_max_requests: int = max_requests  # 暂停前的原始限制

    async def acquire(self) -> None:
        """获取许可，如果窗口已满则等待
        
        算法：
        1. 检查是否处于 retry_after 暂停期，若是则等待恢复
        2. 清理窗口外（过期）的时间戳
        3. 如果窗口内请求数 < 限额，添加当前时间戳并返回
        4. 否则计算等待时间（等待最早请求过期）并 sleep，重复
        """
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
                # 清理过期的时间戳（超出窗口期的请求）
                cutoff = now - self.window_seconds
                while self._timestamps and self._timestamps[0] < cutoff:
                    self._timestamps.popleft()

                if self.max_requests > 0 and len(self._timestamps) < self.max_requests:
                    self._timestamps.append(now)
                    return

                # 等待最早的请求过期，腾出窗口配额
                if self._timestamps:
                    oldest = self._timestamps[0]
                    # +0.01s 避免浮点精度问题导致刚好卡在边界上反复空转
                    wait_time = oldest + self.window_seconds - now + 0.01
                else:
                    wait_time = 1.0  # 安全兜底：max_requests=0 时避免死循环
                await asyncio.sleep(max(0.01, wait_time))

    def update_from_headers(
        self,
        remaining: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """从响应头更新限流参数（用于 The Lens 等动态限流数据源）
        
        Args:
            remaining: 剩余配额数（如 X-RateLimit-Remaining 头）
            retry_after: 建议重试等待秒数（如 Retry-After 头）
        
        逻辑：
        1. 如果 remaining <= 0 且 retry_after 存在，进入暂停状态
        2. 否则根据已消耗 + 剩余配额动态调整 max_requests
        """
        if remaining is not None and remaining <= 0 and retry_after:
            # 暂停直到限流重置，记录恢复时间
            self._original_max_requests = self.max_requests
            self._retry_until = time.monotonic() + retry_after
        elif remaining is not None:
            # 动态调整窗口大小：用已消耗 + 剩余配额推算真实上限
            # 这样即使服务端限额变化，也能自动适配
            current_used = len(self._timestamps)
            if current_used + remaining > 0:
                self.max_requests = current_used + remaining
