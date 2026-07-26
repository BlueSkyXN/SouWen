"""Derived local runtime capability probes for registered providers.

The registry remains the source of truth.  This module only reports declared
providers and local importability; it does not contact upstream services or
validate credentials.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from souwen.registry.adapter import SourceAdapter

LLM_PROVIDER_MODULES: Final[dict[str, str]] = {
    "openai_chat": "souwen.llm.providers.openai_chat",
    "openai_responses": "souwen.llm.providers.openai_responses",
    "anthropic_messages": "souwen.llm.providers.anthropic_messages",
}
WARP_MODE_NAMES: Final[tuple[str, ...]] = (
    "auto",
    "wireproxy",
    "kernel",
    "usque",
    "warp-cli",
    "external",
)
OPTIONAL_EXTRA_MODULES: Final[dict[str, tuple[str, ...]]] = {
    "crawl4ai": ("crawl4ai",),
    "newspaper": ("newspaper",),
    "readability": ("readability",),
    "scraper": ("curl_cffi",),
    "scrapling": ("scrapling.fetchers",),
    "web": ("trafilatura",),
}
REQUIRED_RUNTIME_EXTRAS: Final[frozenset[str]] = frozenset(
    {"crawl4ai", "newspaper", "readability", "scrapling"}
)


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


@dataclass(frozen=True, slots=True)
class FetchProviderRuntimeStatus:
    """Local runtime status for one registered fetch provider."""

    name: str
    runtime_available: bool = False
    runtime_reason: str = ""

    @property
    def available(self) -> bool:
        """Return whether the provider implementation is importable locally."""

        return self.runtime_available


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
    if extra not in REQUIRED_RUNTIME_EXTRAS:
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


def probe_optional_runtime(adapter: SourceAdapter) -> RuntimeProbe:
    """Probe only declared optional packages without loading a configured client.

    This check is suitable for scheduling decisions: client loaders can validate
    credentials or local configuration and therefore must not be treated as a
    universal runtime gate.
    """

    extra = adapter.resolved_package_extra
    if extra not in REQUIRED_RUNTIME_EXTRAS:
        return RuntimeProbe(True)
    modules = OPTIONAL_EXTRA_MODULES.get(extra)
    if modules is None:
        return RuntimeProbe(False, f"{adapter.name}: no runtime probe for extra {extra!r}")
    missing = tuple(module for module in modules if not _module_importable(module))
    if missing:
        return RuntimeProbe(False, f"{adapter.name}: missing modules: {', '.join(missing)}")
    return RuntimeProbe(True)


def sanitize_public_runtime_probe(adapter_name: str, runtime: RuntimeProbe) -> RuntimeProbe:
    """Remove arbitrary loader exception text from a runtime probe.

    Missing-module reasons are derived from maintained metadata and are safe to
    retain. Every other loader failure is replaced with a stable public message.
    """

    if runtime.available:
        return RuntimeProbe(True)
    if runtime.reason.startswith(f"{adapter_name}: missing modules: ") or runtime.reason.startswith(
        "runtime not probed because "
    ):
        return runtime
    return RuntimeProbe(False, f"{adapter_name}: client loader unavailable")


def public_adapter_runtime_probe(adapter: SourceAdapter) -> RuntimeProbe:
    """Return a runtime probe that is safe to expose on public discovery surfaces.

    Loader exceptions remain available to local doctor diagnostics through
    :func:`probe_adapter_runtime`, while REST and other public discovery surfaces use this wrapper.
    """

    return sanitize_public_runtime_probe(adapter.name, probe_adapter_runtime(adapter))


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


def declared_source_names() -> tuple[str, ...]:
    """Return all registry source names."""
    from souwen.registry import all_adapters

    return tuple(sorted(adapter.name for adapter in all_adapters().values()))


def declared_fetch_provider_names() -> tuple[str, ...]:
    """Return all registered fetch provider names."""
    from souwen.registry import fetch_providers

    return tuple(sorted(adapter.name for adapter in fetch_providers()))


def fetch_provider_runtime_projection() -> tuple[FetchProviderRuntimeStatus, ...]:
    """Project registered fetch providers onto their local runtime status."""
    from souwen.registry import fetch_providers

    statuses: list[FetchProviderRuntimeStatus] = []
    for adapter in sorted(fetch_providers(), key=lambda item: item.name):
        runtime = public_adapter_runtime_probe(adapter)
        statuses.append(
            FetchProviderRuntimeStatus(
                name=adapter.name,
                runtime_available=runtime.available,
                runtime_reason=runtime.reason,
            )
        )
    return tuple(statuses)


def declared_llm_protocols() -> tuple[str, ...]:
    """Return LLM protocols declared by the package."""

    return tuple(LLM_PROVIDER_MODULES)


def probe_capabilities() -> dict[str, ProbeResult]:
    """Probe importability-level capabilities for the current process.

    The probe only imports client/provider modules and checks optional package
    specs. It does not instantiate clients, call upstream services, start
    browsers, validate credentials, or inspect host WARP state.
    """

    from souwen.registry import all_adapters, fetch_providers

    source_adapters = list(all_adapters().values())
    declared_sources = tuple(sorted(adapter.name for adapter in source_adapters))
    available_sources, missing_sources = _probe_adapters(source_adapters)

    fetch_adapters = list(fetch_providers())
    declared_fetch = tuple(sorted(adapter.name for adapter in fetch_adapters))
    available_fetch, missing_fetch = _probe_adapters(fetch_adapters)

    warp_modes = WARP_MODE_NAMES

    llm_declared = declared_llm_protocols()
    llm_importable = tuple(
        protocol for protocol in llm_declared if _module_importable(LLM_PROVIDER_MODULES[protocol])
    )
    missing_llm = tuple(protocol for protocol in llm_declared if protocol not in llm_importable)

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
    }


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
    "LLM_PROVIDER_MODULES",
    "OPTIONAL_EXTRA_MODULES",
    "REQUIRED_RUNTIME_EXTRAS",
    "WARP_MODE_NAMES",
    "FetchProviderRuntimeStatus",
    "ProbeResult",
    "RuntimeProbe",
    "declared_fetch_provider_names",
    "declared_llm_protocols",
    "declared_source_names",
    "fetch_provider_runtime_projection",
    "probe_capabilities",
    "probe_adapter_runtime",
    "probe_optional_runtime",
    "probe_modules",
    "probe_results_to_dict",
    "public_adapter_runtime_probe",
    "sanitize_public_runtime_probe",
]
