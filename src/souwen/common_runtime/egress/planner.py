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

    def plan(self, host: str, bounds: EgressBounds) -> EgressDecision:
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
                # Nothing above works either; run at the ceiling anyway so the
                # request still happens and reports its real failure class.
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
    """Chromium reachability: the Playwright package plus its browser bundle."""

    import os
    from pathlib import Path

    try:
        from playwright._impl._driver import compute_driver_executable
    except Exception:
        return False
    driver = compute_driver_executable()
    if driver is None or not Path(driver).exists():
        return False
    browsers_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(
        Path.home() / ".cache" / "ms-playwright"
    )
    root = Path(browsers_root)
    if not root.is_dir():
        return False
    # chromium-<build> 目录存在即视为可用；真实启动失败由 browser pool 报告并降级
    return any(entry.name.startswith("chromium") for entry in root.iterdir() if entry.is_dir())


_planner: EgressPlanner | None = None


def get_egress_planner() -> EgressPlanner:
    global _planner
    if _planner is None:
        _planner = EgressPlanner()
    return _planner


__all__ = ["EgressDecision", "EgressPlanner", "get_egress_planner"]
