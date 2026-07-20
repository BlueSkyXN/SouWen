"""Edition policy helpers for SouWen feature-completeness tiers.

The registry remains the source of truth for sources and fetch providers.  This
module derives their minimum editions and is consumed by runtime gates, doctor,
CLI, Server, MCP and Panel-facing capability declarations.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, cast

from souwen.registry.adapter import FETCH_DOMAIN

if TYPE_CHECKING:
    from souwen.registry.adapter import SourceAdapter


Edition = Literal["basic", "pro", "full"]

EDITIONS: Final[tuple[Edition, ...]] = ("basic", "pro", "full")
EDITION_RANK: Final[dict[Edition, int]] = {
    "basic": 0,
    "pro": 1,
    "full": 2,
}
BASIC_FETCH_PROVIDERS: Final[frozenset[str]] = frozenset({"builtin", "site_crawler", "mcp"})
FULL_FETCH_EXTRAS: Final[frozenset[str]] = frozenset(
    {
        "crawl4ai",
        "scrapling",
        "newspaper",
        "readability",
        "pdf",
        "web2pdf",
    }
)
PREINSTALLED_PLUGIN_MODULES: Final[tuple[str, ...]] = ("superweb2pdf",)
BASIC_WARP_MODES: Final[tuple[str, ...]] = ("auto", "wireproxy", "external")
FULL_WARP_MODES: Final[tuple[str, ...]] = (
    "auto",
    "wireproxy",
    "kernel",
    "usque",
    "warp-cli",
    "external",
)
WARP_MODE_MIN_EDITIONS: Final[dict[str, Edition]] = {
    "auto": "basic",
    "wireproxy": "basic",
    "external": "basic",
    "kernel": "pro",
    "usque": "pro",
    "warp-cli": "pro",
}


class EditionError(ValueError):
    """Raised when a known feature is unavailable in the current edition."""

    def __init__(self, feature: str, required: Edition | str, current: Edition | str):
        self.feature = feature
        self.required = _validate_edition(required, name="required")
        self.current = _validate_edition(current, name="current")
        super().__init__(
            f"{self.feature} requires edition={self.required}, current edition={self.current}"
        )


@dataclass(frozen=True, slots=True)
class EditionPolicy:
    """Metadata describing whether a feature is available in an edition."""

    min_edition: Edition
    available: bool
    reason: str = ""


def _validate_edition(value: Edition | str, *, name: str) -> Edition:
    if value not in EDITION_RANK:
        allowed = ", ".join(EDITIONS)
        raise ValueError(f"{name} must be one of {allowed}; got {value!r}")
    return cast(Edition, value)


def edition_allows(current: Edition | str, required: Edition | str) -> bool:
    """Return whether ``current`` satisfies ``required``."""

    current_edition = _validate_edition(current, name="current")
    required_edition = _validate_edition(required, name="required")
    return EDITION_RANK[current_edition] >= EDITION_RANK[required_edition]


def edition_policy(feature: str, current: Edition | str, required: Edition | str) -> EditionPolicy:
    """Build non-throwing policy metadata for a feature."""

    current_edition = _validate_edition(current, name="current")
    required_edition = _validate_edition(required, name="required")
    available = edition_allows(current_edition, required_edition)
    reason = "" if available else str(EditionError(feature, required_edition, current_edition))
    return EditionPolicy(
        min_edition=required_edition,
        available=available,
        reason=reason,
    )


def ensure_edition_allowed(feature: str, current: Edition | str, required: Edition | str) -> None:
    """Raise ``EditionError`` when a feature is unavailable."""

    current_edition = _validate_edition(current, name="current")
    required_edition = _validate_edition(required, name="required")
    if not edition_allows(current_edition, required_edition):
        raise EditionError(feature, required_edition, current_edition)


def _external_plugin_names() -> set[str]:
    from souwen.registry.views import external_plugins

    return set(external_plugins())


def source_min_edition(adapter: SourceAdapter) -> Edition:
    """Derive the minimum edition for a source adapter."""

    if adapter.domain == FETCH_DOMAIN:
        return fetch_provider_min_edition(adapter)

    if adapter.name in _external_plugin_names():
        return "full"

    if adapter.resolved_package_extra in FULL_FETCH_EXTRAS:
        return "full"

    if adapter.resolved_auth_requirement == "none":
        return "basic"

    if adapter.integration == "scraper":
        return "basic"

    return "pro"


def fetch_provider_min_edition(adapter: SourceAdapter) -> Edition:
    """Derive the minimum edition for a fetch provider adapter."""

    if adapter.name in BASIC_FETCH_PROVIDERS:
        return "basic"

    if adapter.name in _external_plugin_names():
        return "full"

    if adapter.resolved_package_extra in FULL_FETCH_EXTRAS:
        return "full"

    return "pro"


def source_policy(adapter: SourceAdapter, current: Edition | str) -> EditionPolicy:
    """Build non-throwing edition metadata for a source adapter."""

    return edition_policy(
        f"source {adapter.name!r}",
        current=current,
        required=source_min_edition(adapter),
    )


def fetch_provider_policy(adapter: SourceAdapter, current: Edition | str) -> EditionPolicy:
    """Build non-throwing edition metadata for a fetch provider adapter."""

    return edition_policy(
        f"fetch provider {adapter.name!r}",
        current=current,
        required=fetch_provider_min_edition(adapter),
    )


def allowed_warp_modes(current: Edition | str) -> tuple[str, ...]:
    """Return WARP modes exposed by the current edition."""

    current_edition = _validate_edition(current, name="current")
    if current_edition == "basic":
        return BASIC_WARP_MODES
    return FULL_WARP_MODES


def warp_mode_min_edition(mode: str) -> Edition | None:
    """Return the minimum edition for a known WARP mode.

    Unknown modes return ``None`` so callers can preserve their existing
    unknown-mode validation and error shape.
    """

    return WARP_MODE_MIN_EDITIONS.get(mode)


def warp_mode_policy(mode: str, current: Edition | str) -> EditionPolicy:
    """Build non-throwing edition metadata for a known WARP mode."""

    required = warp_mode_min_edition(mode)
    if required is None:
        raise ValueError(f"unknown WARP mode: {mode!r}")
    return edition_policy(f"WARP mode {mode!r}", current=current, required=required)


def ensure_warp_mode_allowed(mode: str, current: Edition | str) -> None:
    """Raise ``EditionError`` when a known WARP mode is unavailable."""

    required = warp_mode_min_edition(mode)
    if required is None:
        return
    ensure_edition_allowed(f"WARP mode {mode!r}", current=current, required=required)


def llm_available(current: Edition | str) -> bool:
    """Return whether LLM features are included in the current edition."""

    return edition_allows(current, "pro")


def _plugin_package_importable(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def plugin_preinstalled(current: Edition | str) -> bool:
    """Return whether the current full runtime has a known preinstalled plugin package."""

    if _validate_edition(current, name="current") != "full":
        return False
    return any(_plugin_package_importable(module) for module in PREINSTALLED_PLUGIN_MODULES)


def ensure_source_allowed(adapter: SourceAdapter, current: Edition | str) -> None:
    """Raise ``EditionError`` when a source adapter is unavailable."""

    ensure_edition_allowed(
        f"source {adapter.name!r}",
        current=current,
        required=source_min_edition(adapter),
    )


def ensure_fetch_provider_allowed(adapter: SourceAdapter, current: Edition | str) -> None:
    """Raise ``EditionError`` when a fetch provider adapter is unavailable."""

    ensure_edition_allowed(
        f"fetch provider {adapter.name!r}",
        current=current,
        required=fetch_provider_min_edition(adapter),
    )


__all__ = [
    "BASIC_FETCH_PROVIDERS",
    "BASIC_WARP_MODES",
    "EDITIONS",
    "EDITION_RANK",
    "FULL_FETCH_EXTRAS",
    "FULL_WARP_MODES",
    "PREINSTALLED_PLUGIN_MODULES",
    "WARP_MODE_MIN_EDITIONS",
    "Edition",
    "EditionError",
    "EditionPolicy",
    "allowed_warp_modes",
    "edition_allows",
    "edition_policy",
    "ensure_edition_allowed",
    "ensure_fetch_provider_allowed",
    "ensure_source_allowed",
    "ensure_warp_mode_allowed",
    "fetch_provider_min_edition",
    "fetch_provider_policy",
    "llm_available",
    "plugin_preinstalled",
    "source_min_edition",
    "source_policy",
    "warp_mode_min_edition",
    "warp_mode_policy",
]
