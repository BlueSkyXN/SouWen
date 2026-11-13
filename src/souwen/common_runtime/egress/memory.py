"""Process-local per-(host, level) success memory for the egress ladder."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from souwen.common_runtime.egress.levels import EgressBounds, EgressLevel

_MEMORY_TTL_SECONDS = 30 * 60.0


@dataclass(slots=True)
class _HostState:
    best_level: EgressLevel | None = None
    failed_levels: set[EgressLevel] = field(default_factory=set)
    updated_at: float = 0.0


class EgressMemory:
    """Remember, per host, the highest level that recently worked.

    Failures are a set: any level that failed more recently than the last
    success is skipped once when choosing the next starting level.
    """

    def __init__(self, *, ttl_seconds: float = _MEMORY_TTL_SECONDS, clock=time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._states: dict[str, _HostState] = {}
        self._lock = threading.Lock()

    def next_level(self, host: str, bounds: EgressBounds) -> EgressLevel:
        """Pick the starting level: last success, else the source minimum,
        climbing past freshly-failed levels up to the source ceiling."""

        with self._lock:
            state = self._get(host)
            if state is None:
                return bounds.min_level
            level = bounds.clamp(state.best_level or bounds.min_level)
            while level in state.failed_levels and int(level) < int(bounds.max_level):
                level = EgressLevel(int(level) + 1)
            return level

    def remember_success(self, host: str, level: EgressLevel) -> None:
        with self._lock:
            state = self._ensure(host)
            if state.best_level is None or level >= state.best_level:
                state.best_level = level
            state.failed_levels.clear()
            state.updated_at = self._clock()

    def remember_failure(self, host: str, level: EgressLevel) -> None:
        with self._lock:
            state = self._ensure(host)
            state.failed_levels.add(level)
            state.updated_at = self._clock()

    def status(self, host: str) -> dict[str, str | None]:
        """Safe projection for /sources and doctor output."""

        with self._lock:
            state = self._states.get(host)
            if state is None:
                return {"best_level": None, "last_failure": None}
            fresh = self._clock() - state.updated_at <= self._ttl
            return {
                "best_level": state.best_level.label if fresh and state.best_level else None,
                "last_failure": (
                    max(state.failed_levels).label if fresh and state.failed_levels else None
                ),
            }

    def _get(self, host: str) -> _HostState | None:
        state = self._states.get(host)
        if state is None or self._clock() - state.updated_at > self._ttl:
            return None
        return state

    def _ensure(self, host: str) -> _HostState:
        state = self._states.get(host)
        if state is None:
            state = _HostState()
            self._states[host] = state
        return state


_memory: EgressMemory | None = None
_memory_lock = threading.Lock()


def get_egress_memory() -> EgressMemory:
    global _memory
    with _memory_lock:
        if _memory is None:
            _memory = EgressMemory()
        return _memory


__all__ = ["EgressMemory", "get_egress_memory"]
