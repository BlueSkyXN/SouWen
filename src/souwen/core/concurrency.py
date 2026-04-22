"""core/concurrency.py — 并发度信号量（per-event-loop）

实现（D12）：
  用 `WeakKeyDictionary[AbstractEventLoop, Semaphore]` 存储 per-loop Semaphore。

权衡（v1-初步定义 §4.2）：
  - asyncio.Semaphore 内部会绑定创建时的 event loop；跨 loop 使用会炸。
  - ContextVar 是上下文（async task）级别的一致性，**不跨 loop 隔离**；
    在 `asyncio.new_event_loop()` 场景下会把老 loop 的 Semaphore 漏到新 loop。
  - WeakKeyDictionary 以 loop 为 key，与 Semaphore 的隐式 loop 绑定保持一致；
    loop 被 GC 后字典项自动清理，不内存泄漏。
  - 不依赖 AbstractEventLoop 的未定义属性，不需 type: ignore。
"""

from __future__ import annotations

import asyncio
import os
import weakref

# 默认全局并发度上限；通过 SOUWEN_MAX_CONCURRENCY 环境变量覆盖
_DEFAULT_MAX_CONCURRENCY = 10

#: 按 channel 分开存储的 per-loop Semaphore 映射。
#: WeakKeyDictionary 会在 loop 被 GC 时自动清理对应 Semaphore。
_sem_maps: dict[str, "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]"] = {
    "search": weakref.WeakKeyDictionary(),
    "web": weakref.WeakKeyDictionary(),
}


def get_max_concurrency() -> int:
    """读取并发上限，允许通过环境变量 `SOUWEN_MAX_CONCURRENCY` 覆盖。

    非正整数会被忽略，回退到默认值 10。
    """
    raw = os.environ.get("SOUWEN_MAX_CONCURRENCY")
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return _DEFAULT_MAX_CONCURRENCY


def get_semaphore(
    channel: str = "search",
    size: int | None = None,
) -> asyncio.Semaphore:
    """返回当前运行 loop 的 Semaphore（不存在则创建）。

    同一个 event loop 多次调用返回**同一个** Semaphore；
    不同 event loop 之间返回**独立** Semaphore（防止 asyncio.Semaphore
    绑定错 loop 的经典坑）。

    Args:
        channel: "search"（论文/专利门面）或 "web"（网页聚合门面）。
            两个 channel 互相独立，避免跨门面相互阻塞。
        size: 首次创建时的初始许可数；None 用 `get_max_concurrency()`。
            已存在则忽略 size。

    Returns:
        与当前 running event loop 绑定的 `asyncio.Semaphore`。

    Raises:
        RuntimeError: 没有 running event loop（在协程外调用）。
    """
    if channel not in _sem_maps:
        raise ValueError(f"unknown channel {channel!r}; expected 'search' or 'web'")
    loop = asyncio.get_running_loop()
    sem_map = _sem_maps[channel]
    sem = sem_map.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(size if size is not None else get_max_concurrency())
        sem_map[loop] = sem
    return sem


def clear_semaphore(channel: str | None = None) -> None:
    """清除指定 channel 的所有 per-loop Semaphore（主要给测试使用）。

    Args:
        channel: 指定要清除的 channel；None 表示清除所有 channel。
    """
    targets = [channel] if channel else list(_sem_maps.keys())
    for ch in targets:
        if ch in _sem_maps:
            _sem_maps[ch] = weakref.WeakKeyDictionary()
