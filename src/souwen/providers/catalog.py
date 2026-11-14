"""Deterministic discovery of built-in Provider v2 manifests."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator
from types import ModuleType

from souwen.platform.manifest_registry import ManifestRegistry, ProviderManifest


_PROVIDER_NAMESPACES = (
    "souwen.providers.fetch_sources",
    "souwen.providers.information_sources",
    "souwen.providers.llm_sources",
)


def _provider_packages(namespace: str) -> Iterator[str]:
    package = importlib.import_module(namespace)
    for module in sorted(pkgutil.iter_modules(package.__path__), key=lambda item: item.name):
        if module.ispkg:
            yield f"{namespace}.{module.name}"


def _manifests_from(module: ModuleType) -> tuple[ProviderManifest, ...]:
    manifests = tuple(
        value for value in vars(module).values() if isinstance(value, ProviderManifest)
    )
    if not manifests:
        raise RuntimeError(f"provider manifest module exports no manifests: {module.__name__}")
    return manifests


def builtin_provider_manifests() -> tuple[ProviderManifest, ...]:
    """Load every built-in manifest without importing provider adapters or runtime clients."""

    manifests = tuple(
        manifest
        for namespace in _PROVIDER_NAMESPACES
        for package in _provider_packages(namespace)
        for manifest in _manifests_from(importlib.import_module(f"{package}.manifest"))
    )
    registry = ManifestRegistry()
    registrations = registry.discover(manifests)
    if any(not registration.accepted for registration in registrations):
        raise RuntimeError("built-in provider manifests contain duplicate package or adapter IDs")
    return tuple(sorted(registry.packages, key=lambda manifest: manifest.id))


def register_manifest_egress_bounds(
    manifests: tuple[ProviderManifest, ...] | None = None,
) -> None:
    """Publish every manifest's declared min/max_egress to the egress module.

    SPEC 5.2：源的阶梯边界由 manifest 声明。common_runtime 不能反向 import
    providers（架构门禁 DEP-004），因此由本模块把声明推进注册表。
    """

    from souwen.common_runtime.egress import EgressBounds, register_egress_bounds
    from souwen.common_runtime.egress.levels import EgressLevel

    levels = {level.label: level for level in EgressLevel}
    for manifest in manifests if manifests is not None else builtin_provider_manifests():
        network = getattr(manifest, "network", None)
        min_name = getattr(network, "min_egress", None)
        max_name = getattr(network, "max_egress", None)
        if min_name is None or max_name is None:
            continue
        register_egress_bounds(
            manifest.id,
            EgressBounds(min_level=levels[min_name], max_level=levels[max_name]),
        )


__all__ = ["builtin_provider_manifests", "register_manifest_egress_bounds"]
