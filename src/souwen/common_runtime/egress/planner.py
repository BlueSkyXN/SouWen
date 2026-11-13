"""The planner ties source bounds, host memory, and runtime availability."""

from __future__ import annotations

from dataclasses import dataclass

from souwen.common_runtime.egress.levels import EgressBounds, EgressLevel
from souwen.common_runtime.egress.memory import EgressMemory, get_egress_memory


@dataclass(frozen=True, slots=True)
class EgressDecision:
    """One resolved acquisition plan for a request."""

    level: EgressLevel
    proxy: str | None
    reason: str


class EgressPlanner:
    """Decide the egress level for one request and ingest outcomes.

    ``proxy`` availability gates the PROXY level: without WARP or a user
    proxy the planner skips straight past it. ``browser`` availability gates
    the BROWSER level the same way (SPEC 5.5: no Playwright → no error).
    """

    def __init__(
        self,
        memory: EgressMemory | None = None,
        *,
        proxy_provider=None,
        browser_available=None,
    ) -> None:
        self._memory = memory or get_egress_memory()
        self._proxy_provider = proxy_provider
        self._browser_available = browser_available

    def effective_bounds(self, bounds: EgressBounds) -> EgressBounds:
        """Lower the ceiling to the highest level actually available (SPEC 5.5).

        Browser missing → ladder works within the first three levels; proxy
        missing → PROXY is not executable, so the ceiling drops accordingly.
        """

        max_level = bounds.max_level
        if max_level is EgressLevel.BROWSER and not self._browser_ready():
            max_level = EgressLevel.PROXY
        if max_level is EgressLevel.PROXY and not self._resolve_proxy():
            if bounds.min_level is EgressLevel.PROXY:
                max_level = EgressLevel.PROXY  # min 就在 proxy：保持，报告真实失败
            else:
                max_level = EgressLevel.IMPERSONATE
        return EgressBounds(min_level=bounds.min_level, max_level=max_level)

    def plan(self, host: str, bounds: EgressBounds) -> EgressDecision:
        bounds = self.effective_bounds(bounds)
        level = self._memory.next_level(host, bounds)
        reason = "remembered-or-min"
        while True:
            if level is EgressLevel.PROXY and not self._resolve_proxy():
                reason = "no-proxy-configured"
            elif level is EgressLevel.BROWSER and not self._browser_ready():
                reason = "browser-unavailable"
            else:
                break
            if int(level) >= int(bounds.max_level):
                # 有效天花板：请求仍在此级执行，报告真实失败类别
                return EgressDecision(
                    bounds.max_level, self._proxy_for_level(bounds.max_level), reason
                )
            level = EgressLevel(int(level) + 1)
        return EgressDecision(level, self._proxy_for_level(level), reason)

    def report_success(self, host: str, level: EgressLevel) -> None:
        self._memory.remember_success(host, level)

    def report_failure(self, host: str, level: EgressLevel) -> None:
        self._memory.remember_failure(host, level)

    def _proxy_for_level(self, level: EgressLevel) -> str | None:
        if level is EgressLevel.PROXY:
            return self._resolve_proxy()
        return None

    def _resolve_proxy(self) -> str | None:
        if self._proxy_provider is None:
            from souwen.config import get_config

            self._proxy_provider = lambda: get_config().get_proxy()
        proxy = self._proxy_provider()
        return proxy or None

    def _browser_ready(self) -> bool:
        if self._browser_available is None:
            self._browser_available = _default_browser_availability
        return self._browser_available()


def _default_browser_availability() -> bool:
    from souwen.common_runtime.provider_support.browser_fetch import chromium_available

    return chromium_available()


_planner: EgressPlanner | None = None


def get_egress_planner() -> EgressPlanner:
    global _planner
    if _planner is None:
        _planner = EgressPlanner()
    return _planner


__all__ = ["EgressDecision", "EgressPlanner", "get_egress_planner"]
