"""Construction-scoped control for legacy source-channel overrides."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


_SOURCE_CHANNEL_OVERRIDES_ENABLED: ContextVar[bool] = ContextVar(
    "souwen_source_channel_overrides_enabled",
    default=True,
)
_REVIEWED_SOURCE_PROXY: ContextVar[str | None] = ContextVar(
    "souwen_reviewed_source_proxy",
    default=None,
)
_REVIEWED_SOURCE_TIMEOUT_SECONDS: ContextVar[float | None] = ContextVar(
    "souwen_reviewed_source_timeout_seconds",
    default=None,
)
_REVIEWED_SOURCE_MAX_RETRIES: ContextVar[int | None] = ContextVar(
    "souwen_reviewed_source_max_retries",
    default=None,
)


def source_channel_overrides_enabled() -> bool:
    """Return whether legacy clients may read source-level transport overrides."""

    return _SOURCE_CHANNEL_OVERRIDES_ENABLED.get()


def reviewed_source_proxy() -> str | None:
    """Return the proxy explicitly admitted by the active Provider v2 manifest."""

    return _REVIEWED_SOURCE_PROXY.get()


def reviewed_source_timeout_seconds() -> float | None:
    """Return the timeout admitted by the active Provider v2 runtime config."""

    return _REVIEWED_SOURCE_TIMEOUT_SECONDS.get()


def reviewed_source_max_retries() -> int | None:
    """Return the retry count admitted by the active Provider v2 runtime config."""

    return _REVIEWED_SOURCE_MAX_RETRIES.get()


@contextmanager
def without_source_channel_overrides(
    *,
    proxy: str | None = None,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
) -> Iterator[None]:
    """Keep a Provider v2 bridge on its reviewed static transport during construction."""

    enabled_token = _SOURCE_CHANNEL_OVERRIDES_ENABLED.set(False)
    proxy_token = _REVIEWED_SOURCE_PROXY.set(proxy)
    timeout_token = _REVIEWED_SOURCE_TIMEOUT_SECONDS.set(timeout_seconds)
    retries_token = _REVIEWED_SOURCE_MAX_RETRIES.set(max_retries)
    try:
        yield
    finally:
        _REVIEWED_SOURCE_MAX_RETRIES.reset(retries_token)
        _REVIEWED_SOURCE_TIMEOUT_SECONDS.reset(timeout_token)
        _REVIEWED_SOURCE_PROXY.reset(proxy_token)
        _SOURCE_CHANNEL_OVERRIDES_ENABLED.reset(enabled_token)


__all__ = [
    "reviewed_source_proxy",
    "reviewed_source_max_retries",
    "reviewed_source_timeout_seconds",
    "source_channel_overrides_enabled",
    "without_source_channel_overrides",
]
