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

# Sources allowed to escalate to Chromium. Managed centrally so the scraper
# layer stays free of per-source lists.
BROWSER_CAPABLE_SOURCES: frozenset[str] = frozenset(
    {
        # DDG family and its site-search aliases
        "duckduckgo",
        "duckduckgo_news",
        "duckduckgo_images",
        "duckduckgo_videos",
        "hostloc",
        "nodeseek",
        "v2ex",
        "coolapk",
        "xiaohongshu",
        # HTML engines blocked for datacenter IPs
        "baidu",
        "bing",
        "bing_cn",
        "brave",
        "google",
        "mojeek",
        "startpage",
        "yandex",
        # others waiting on the browser verdict
        "csdn",
        "google_patents",
    }
)


def egress_bounds_for(source_id: str) -> EgressBounds:
    """Resolve the ladder bounds for one source id."""

    if source_id in BROWSER_CAPABLE_SOURCES:
        return EgressBounds(min_level=EgressLevel.IMPERSONATE, max_level=EgressLevel.BROWSER)
    return _DEFAULT_BOUNDS


__all__ = [
    "BROWSER_CAPABLE_SOURCES",
    "EgressBounds",
    "EgressLevel",
    "egress_bounds_for",
    "parse_egress_level",
]
