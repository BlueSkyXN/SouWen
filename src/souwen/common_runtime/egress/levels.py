"""Egress level enumeration and source bounds."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class EgressLevel(IntEnum):
    """Egress levels ordered cheapest-first; the ladder only climbs."""

    DIRECT = 0
    IMPERSONATE = 1
    PROXY = 2
    BROWSER = 3

    @property
    def label(self) -> str:
        return self.name.lower()


_LEVEL_NAMES = {level.label: level for level in EgressLevel}


def parse_egress_level(value: str) -> EgressLevel:
    level = _LEVEL_NAMES.get(value.strip().lower())
    if level is None:
        raise ValueError(f"unknown egress level: {value!r}")
    return level


@dataclass(frozen=True, slots=True)
class EgressBounds:
    """Per-source ladder bounds; defaults mirror pre-ladder behaviour.

    Most sources start at IMPERSONATE (the long-standing curl_cffi default)
    and may climb to PROXY. Scrapers that opt into the browser level declare
    ``max_level=BROWSER``.
    """

    min_level: EgressLevel = EgressLevel.IMPERSONATE
    max_level: EgressLevel = EgressLevel.PROXY

    def __post_init__(self) -> None:
        if self.min_level > self.max_level:
            raise ValueError("min_level must not exceed max_level")

    def clamp(self, level: EgressLevel) -> EgressLevel:
        return max(self.min_level, min(self.max_level, level))


_DEFAULT_BOUNDS = EgressBounds()

# 出口级别字面量（与 manifest NetworkDeclaration.min/max_egress 同一张表）
_LEVELS_BY_NAME: dict[str, EgressLevel] = {level.label: level for level in EgressLevel}

# 源 id → 声明边界的注册表。由 providers.catalog 在进程启动时填充
# （common_runtime 不允许反向 import providers，架构门禁 DEP-004）。
# 源 id → 声明边界的注册表。由 providers.catalog 的
# register_manifest_egress_bounds() 在 runtime 组装前填充（common_runtime
# 不允许反向 import providers，架构门禁 DEP-004）。
_DECLARED_BOUNDS: dict[str, EgressBounds] = {}


def register_egress_bounds(source_id: str, bounds: EgressBounds) -> None:
    """Register one source's manifest-declared bounds (called by providers.catalog)."""

    _DECLARED_BOUNDS[source_id] = bounds


def egress_bounds_for(source_id: str) -> EgressBounds:
    """Resolve the ladder bounds declared by the source manifest (SPEC 5.2).

    声明是唯一事实来源：browser-capable 由源自己的 ``max_egress: browser``
    声明，不再维护中心源 id 清单。未注册的 id（内部 id、测试桩、注册前
    查询）回退默认边界。
    """

    return _DECLARED_BOUNDS.get(source_id, _DEFAULT_BOUNDS)


__all__ = [
    "EgressBounds",
    "EgressLevel",
    "egress_bounds_for",
    "parse_egress_level",
    "register_egress_bounds",
]
