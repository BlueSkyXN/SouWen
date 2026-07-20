"""Derived feature matrix for SouWen edition capabilities.

This module is a compatibility/query layer over :mod:`souwen.editions` and the
registry. It does not maintain a second source/provider list and it performs no
network, browser, WARP, or credential checks.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, cast

from souwen.editions import (
    EDITIONS,
    PREINSTALLED_PLUGIN_MODULES,
    Edition,
    allowed_warp_modes,
    edition_allows,
    fetch_provider_min_edition,
    fetch_provider_policy,
    llm_available,
    plugin_preinstalled,
    source_min_edition,
    source_policy,
)
from souwen.registry.adapter import SourceAdapter

LLM_PROVIDER_MODULES: Final[dict[str, str]] = {
    "openai_chat": "souwen.llm.providers.openai_chat",
    "openai_responses": "souwen.llm.providers.openai_responses",
    "anthropic_messages": "souwen.llm.providers.anthropic_messages",
}
MCP_MODULE: Final[str] = "mcp"
OPTIONAL_EXTRA_MODULES: Final[dict[str, tuple[str, ...]]] = {
    "crawl4ai": ("crawl4ai",),
    "mcp": ("mcp",),
    "newspaper": ("newspaper",),
    "pdf": ("pymupdf4llm",),
    "readability": ("readability",),
    "scraper": ("curl_cffi",),
    "scrapling": ("scrapling.fetchers",),
    "web": ("trafilatura",),
}
SURFACE_ROUTE_MIN_EDITIONS: Final[dict[str, Edition]] = {
    "/api/v1/summarize": "pro",
    "/api/v1/fetch/summarize": "pro",
}


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Declared versus currently importable capability metadata."""

    declared: object
    available: object
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RuntimeProbe:
    """Importability result for one registry adapter in the current process."""

    available: bool
    reason: str = ""


def _resolve_edition(edition: Edition | str | None) -> Edition:
    if edition is None:
        from souwen.config import get_config

        return get_config().edition

    edition_allows(edition, "basic")
    return cast(Edition, edition)


def _module_importable(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def probe_modules(module_names: Iterable[str]) -> RuntimeProbe:
    """Probe a set of module names without importing or instantiating them."""

    names = tuple(module_names)
    missing = tuple(module for module in names if not _module_importable(module))
    if missing:
        return RuntimeProbe(False, f"missing modules: {', '.join(missing)}")
    return RuntimeProbe(True)


def probe_adapter_runtime(adapter: SourceAdapter) -> RuntimeProbe:
    """Probe an adapter loader and its declared optional runtime modules.

    This is deliberately a local importability check.  It does not instantiate
    clients, inspect credentials, start browsers or contact upstream services.
    """

    try:
        adapter.client_loader()
    except Exception as exc:
        return RuntimeProbe(False, f"{adapter.name}: {type(exc).__name__}: {exc}")

    extra = adapter.resolved_package_extra
    if not extra:
        return RuntimeProbe(True)

    modules = OPTIONAL_EXTRA_MODULES.get(extra)
    if modules is None:
        return RuntimeProbe(False, f"{adapter.name}: no runtime probe for extra {extra!r}")

    missing = tuple(module for module in modules if not _module_importable(module))
    if missing:
        return RuntimeProbe(
            False,
            f"{adapter.name}: missing modules: {', '.join(missing)}",
        )
    return RuntimeProbe(True)


def _probe_adapters(adapters: list[SourceAdapter]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    available: list[str] = []
    missing_reasons: list[str] = []

    for adapter in sorted(adapters, key=lambda item: item.name):
        runtime = probe_adapter_runtime(adapter)
        if runtime.available:
            available.append(adapter.name)
        else:
            missing_reasons.append(runtime.reason)

    return tuple(available), tuple(missing_reasons)


def _missing_reason(missing_reasons: tuple[str, ...]) -> str:
    if not missing_reasons:
        return ""
    return "; ".join(missing_reasons)


def _probe_package_extras(adapters: list[SourceAdapter]) -> ProbeResult:
    declared: dict[str, tuple[str, ...]] = {}
    available: list[str] = []
    missing_reasons: list[str] = []
    unknown_extras: set[str] = set()

    for adapter in sorted(adapters, key=lambda item: item.name):
        extra = adapter.resolved_package_extra
        if not extra:
            continue
        modules = OPTIONAL_EXTRA_MODULES.get(extra)
        if not modules:
            unknown_extras.add(extra)
            declared.setdefault(extra, ())
            continue
        declared.setdefault(extra, modules)

    for extra, modules in sorted(declared.items()):
        if extra in unknown_extras:
            missing_reasons.append(f"{extra}: no optional module probe is declared")
            continue
        missing = tuple(module for module in modules if not _module_importable(module))
        if not missing:
            available.append(extra)
            continue
        missing_reasons.append(f"{extra}: missing modules: {', '.join(missing)}")

    return ProbeResult(
        declared=declared,
        available=tuple(available),
        reason=_missing_reason(tuple(missing_reasons)),
    )


def declared_source_names(edition: Edition | str | None = None) -> tuple[str, ...]:
    """Return registry source names declared for ``edition``."""

    current = _resolve_edition(edition)
    from souwen.registry import all_adapters

    return tuple(
        sorted(
            adapter.name
            for adapter in all_adapters().values()
            if source_policy(adapter, current).available
        )
    )


def declared_fetch_provider_names(edition: Edition | str | None = None) -> tuple[str, ...]:
    """Return fetch provider names declared for ``edition``."""

    current = _resolve_edition(edition)
    from souwen.registry import fetch_providers

    return tuple(
        sorted(
            adapter.name
            for adapter in fetch_providers()
            if fetch_provider_policy(adapter, current).available
        )
    )


def declared_llm_protocols(edition: Edition | str | None = None) -> tuple[str, ...]:
    """Return LLM protocols declared for ``edition``."""

    current = _resolve_edition(edition)
    if not llm_available(current):
        return ()
    return tuple(LLM_PROVIDER_MODULES)


def probe_capabilities(edition: Edition | str | None = None) -> dict[str, ProbeResult]:
    """Probe importability-level capabilities for the current process.

    The probe only imports client/provider modules and checks optional package
    specs. It does not instantiate clients, call upstream services, start
    browsers, validate credentials, or inspect host WARP state.
    """

    current = _resolve_edition(edition)

    from souwen.registry import all_adapters, fetch_providers

    source_adapters = [
        adapter for adapter in all_adapters().values() if source_policy(adapter, current).available
    ]
    declared_sources = tuple(sorted(adapter.name for adapter in source_adapters))
    available_sources, missing_sources = _probe_adapters(source_adapters)

    fetch_adapters = [
        adapter
        for adapter in fetch_providers()
        if fetch_provider_policy(adapter, current).available
    ]
    declared_fetch = tuple(sorted(adapter.name for adapter in fetch_adapters))
    available_fetch, missing_fetch = _probe_adapters(fetch_adapters)

    warp_modes = tuple(allowed_warp_modes(current))

    llm_declared = declared_llm_protocols(current)
    llm_importable = tuple(
        protocol for protocol in llm_declared if _module_importable(LLM_PROVIDER_MODULES[protocol])
    )
    missing_llm = tuple(protocol for protocol in llm_declared if protocol not in llm_importable)

    mcp_declared = "mcp" in declared_fetch
    mcp_importable = _module_importable(MCP_MODULE) if mcp_declared else False

    plugin_declared = edition_allows(current, "full")
    plugin_available = plugin_preinstalled(current)

    return {
        "sources": ProbeResult(
            declared=declared_sources,
            available=available_sources,
            reason=_missing_reason(missing_sources),
        ),
        "fetch_providers": ProbeResult(
            declared=declared_fetch,
            available=available_fetch,
            reason=_missing_reason(missing_fetch),
        ),
        "package_extras": _probe_package_extras(source_adapters + fetch_adapters),
        "warp_modes": ProbeResult(declared=warp_modes, available=warp_modes),
        "llm_protocols": ProbeResult(
            declared=llm_declared,
            available=llm_importable,
            reason=f"missing provider modules: {', '.join(missing_llm)}" if missing_llm else "",
        ),
        "mcp": ProbeResult(
            declared=mcp_declared,
            available=mcp_importable,
            reason=f"module {MCP_MODULE!r} is not importable"
            if mcp_declared and not mcp_importable
            else "",
        ),
        "plugin_preinstalled": ProbeResult(
            declared=plugin_declared,
            available=plugin_available,
            reason=(
                "no preinstalled plugin module importable: "
                f"{', '.join(PREINSTALLED_PLUGIN_MODULES)}"
            )
            if plugin_declared and not plugin_available
            else "",
        ),
    }


def edition_capabilities(edition: Edition | str | None = None) -> dict[str, object]:
    """Return the legacy `/whoami` edition capability payload."""

    current = _resolve_edition(edition)
    return {
        "llm": bool(declared_llm_protocols(current)),
        "warp_modes": list(allowed_warp_modes(current)),
        "fetch_providers": list(declared_fetch_provider_names(current)),
        "plugin_preinstalled": plugin_preinstalled(current),
    }


def route_min_edition(path: str) -> Edition | None:
    """Return the declared minimum edition for a route with explicit feature gating."""

    return SURFACE_ROUTE_MIN_EDITIONS.get(path)


def probe_results_to_dict(results: dict[str, ProbeResult]) -> dict[str, dict[str, object]]:
    """Convert probe dataclasses into a JSON-serializable mapping."""

    return {
        key: {
            "declared": result.declared,
            "available": result.available,
            "reason": result.reason,
        }
        for key, result in results.items()
    }


__all__ = [
    "EDITIONS",
    "LLM_PROVIDER_MODULES",
    "MCP_MODULE",
    "OPTIONAL_EXTRA_MODULES",
    "SURFACE_ROUTE_MIN_EDITIONS",
    "Edition",
    "ProbeResult",
    "RuntimeProbe",
    "allowed_warp_modes",
    "declared_fetch_provider_names",
    "declared_llm_protocols",
    "declared_source_names",
    "edition_capabilities",
    "fetch_provider_min_edition",
    "probe_capabilities",
    "probe_adapter_runtime",
    "probe_modules",
    "probe_results_to_dict",
    "route_min_edition",
    "source_min_edition",
]
