"""Egress levels, per-host memory, and the level planner (SPEC 5).

Four levels: ``direct`` (plain httpx), ``impersonate`` (curl_cffi browser
fingerprint), ``proxy`` (WARP or user proxy), ``browser`` (Chromium via the
shared Playwright pool). Each source declares bounds; the planner starts a
host at its last successful level and climbs on failure, one level at a
time, never above the source's ceiling. Memory is process-local.
"""

from souwen.common_runtime.egress.levels import EgressLevel, egress_bounds_for
from souwen.common_runtime.egress.memory import EgressMemory, get_egress_memory
from souwen.common_runtime.egress.planner import (
    EgressDecision,
    EgressPlanner,
    get_egress_planner,
)

__all__ = [
    "EgressDecision",
    "EgressLevel",
    "EgressMemory",
    "EgressPlanner",
    "egress_bounds_for",
    "get_egress_memory",
    "get_egress_planner",
]
