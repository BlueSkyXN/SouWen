"""SouWen 限流器测试"""

import time

import pytest

from souwen.rate_limiter import (
    RateLimiterBase,
    SlidingWindowLimiter,
    TokenBucketLimiter,
)


class TestRateLimiterBase:
    """抽象基类测试"""

    def test_cannot_instantiate(self):
        """RateLimiterBase 不能直接实例化"""
        with pytest.raises(TypeError):
            RateLimiterBase()

    def test_subclass_must_implement_acquire(self):
        """子类必须实现 acquire"""

        class BadLimiter(RateLimiterBase):
            pass

        with pytest.raises(TypeError):
            BadLimiter()

    def test_update_from_headers_default_noop(self):
        """默认 update_from_headers 是空操作"""

        class SimpleLimiter(RateLimiterBase):
            async def acquire(self):
                pass

        limiter = SimpleLimiter()
        limiter.update_from_headers(remaining=5, retry_after=1.0)  # 不抛异常


class TestTokenBucketLimiter:
    """令牌桶限流器测试"""

    def test_rate_zero_raises(self):
        """rate=0 抛出 ValueError"""
        with pytest.raises(ValueError, match="rate"):
            TokenBucketLimiter(rate=0)

    def test_rate_negative_raises(self):
        """负 rate 抛出 ValueError"""
        with pytest.raises(ValueError):
            TokenBucketLimiter(rate=-1)

    def test_default_burst(self):
        """默认 burst = max(1, int(rate))"""
        limiter = TokenBucketLimiter(rate=0.5)
        assert limiter.burst == 1
        limiter2 = TokenBucketLimiter(rate=10)
        assert limiter2.burst == 10

    def test_custom_burst(self):
        """自定义 burst"""
        limiter = TokenBucketLimiter(rate=5, burst=20)
        assert limiter.burst == 20

    async def test_acquire_no_block_when_tokens_available(self):
        """有令牌时 acquire 不阻塞"""
        limiter = TokenBucketLimiter(rate=100, burst=10)
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    async def test_burst_allows_multiple_fast_acquires(self):
        """burst 允许连续快速获取多个令牌"""
        limiter = TokenBucketLimiter(rate=10, burst=5)
        start = time.monotonic()
        for _ in range(5):
            await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.2

    async def test_acquire_blocks_when_empty(self):
        """桶空后 acquire 会等待"""
        limiter = TokenBucketLimiter(rate=10, burst=1)
        await limiter.acquire()  # 用掉唯一的令牌
        start = time.monotonic()
        await limiter.acquire()  # 需要等待补充
        elapsed = time.monotonic() - start
        assert elapsed >= 0.05  # 至少等了一点时间


class TestSlidingWindowLimiter:
    """滑动窗口限流器测试"""

    async def test_acquire_within_window(self):
        """窗口内请求不阻塞"""
        limiter = SlidingWindowLimiter(max_requests=10, window_seconds=60)
        start = time.monotonic()
        for _ in range(5):
            await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.5

    async def test_acquire_all_slots(self):
        """填满窗口后下一个会阻塞"""
        limiter = SlidingWindowLimiter(max_requests=2, window_seconds=0.2)
        await limiter.acquire()
        await limiter.acquire()
        start = time.monotonic()
        await limiter.acquire()  # 需要等最早的过期
        elapsed = time.monotonic() - start
        assert elapsed >= 0.1

    def test_update_from_headers_with_retry_after(self):
        """retry_after 设置暂停时间"""
        limiter = SlidingWindowLimiter(max_requests=10, window_seconds=60)
        limiter.update_from_headers(remaining=0, retry_after=5.0)
        assert limiter._retry_until > 0

    def test_update_from_headers_remaining_adjusts_max(self):
        """remaining > 0 动态调整 max_requests"""
        limiter = SlidingWindowLimiter(max_requests=10, window_seconds=60)
        limiter.update_from_headers(remaining=50)
        assert limiter.max_requests == 50

    def test_update_from_headers_noop_without_args(self):
        """无参数调用不修改状态"""
        limiter = SlidingWindowLimiter(max_requests=10, window_seconds=60)
        limiter.update_from_headers()
        assert limiter.max_requests == 10

    async def test_retry_after_resets_after_wait(self):
        """retry_after 暂停后自动恢复"""
        limiter = SlidingWindowLimiter(max_requests=5, window_seconds=60)
        limiter.update_from_headers(remaining=0, retry_after=0.1)
        await limiter.acquire()  # 等 0.1s 后自动恢复
        assert limiter._retry_until == 0
