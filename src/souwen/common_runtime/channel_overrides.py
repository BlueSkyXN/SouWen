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


def source_channel_overrides_enabled() -> bool:
    """Return whether legacy clients may read source-level transport overrides."""

    return _SOURCE_CHANNEL_OVERRIDES_ENABLED.get()


def reviewed_source_proxy() -> str | None:
    """Return the proxy explicitly admitted by the active Provider v2 manifest."""

    return _REVIEWED_SOURCE_PROXY.get()


@contextmanager
def without_source_channel_overrides(*, proxy: str | None = None) -> Iterator[None]:
    """Keep a Provider v2 bridge on its reviewed static transport during construction."""

    enabled_token = _SOURCE_CHANNEL_OVERRIDES_ENABLED.set(False)
    proxy_token = _REVIEWED_SOURCE_PROXY.set(proxy)
    try:
        yield
    finally:
        _REVIEWED_SOURCE_PROXY.reset(proxy_token)
        _SOURCE_CHANNEL_OVERRIDES_ENABLED.reset(enabled_token)


__all__ = [
    "reviewed_source_proxy",
    "source_channel_overrides_enabled",
    "without_source_channel_overrides",
]
