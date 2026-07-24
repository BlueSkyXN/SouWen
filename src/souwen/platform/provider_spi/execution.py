"""Execution deadline and cancellation context passed from Core to providers."""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field

from souwen.platform.provider_spi.errors import ProviderError, ProviderErrorCode


MAX_EXECUTION_SECONDS = 120.0


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """A provider-call budget using an absolute monotonic deadline."""

    deadline_monotonic: float
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    max_remaining_seconds: float = MAX_EXECUTION_SECONDS

    def __post_init__(self) -> None:
        if not math.isfinite(self.deadline_monotonic):
            raise ValueError("deadline_monotonic must be finite")
        if not 0 < self.max_remaining_seconds <= MAX_EXECUTION_SECONDS:
            raise ValueError(f"max_remaining_seconds must be in (0, {MAX_EXECUTION_SECONDS}]")

    @classmethod
    def with_timeout(
        cls,
        timeout_seconds: float,
        *,
        cancel_event: asyncio.Event | None = None,
    ) -> ExecutionContext:
        """Create an absolute deadline within the target hard maximum."""

        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= MAX_EXECUTION_SECONDS:
            raise ValueError(f"timeout_seconds must be in (0, {MAX_EXECUTION_SECONDS}]")
        return cls(
            deadline_monotonic=time.monotonic() + timeout_seconds,
            cancel_event=cancel_event if cancel_event is not None else asyncio.Event(),
            max_remaining_seconds=timeout_seconds,
        )

    @property
    def cancelled(self) -> bool:
        """Whether the caller has signalled cancellation."""

        return self.cancel_event.is_set()

    @property
    def remaining_seconds(self) -> float:
        """Return the non-negative, bounded time available for the call."""

        return max(0.0, min(self.deadline_monotonic - time.monotonic(), self.max_remaining_seconds))

    @property
    def expired(self) -> bool:
        """Whether no provider-call time remains."""

        return self.remaining_seconds <= 0

    def raise_if_cancelled_or_expired(self) -> None:
        """Raise a safe canonical provider error before starting more work."""

        if self.cancelled or self.expired:
            code = (
                ProviderErrorCode.CANCELLED
                if self.cancelled
                else ProviderErrorCode.DEADLINE_EXCEEDED
            )
            raise ProviderError(code)


__all__ = ["ExecutionContext", "MAX_EXECUTION_SECONDS"]
