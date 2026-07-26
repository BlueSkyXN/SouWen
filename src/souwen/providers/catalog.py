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


__all__ = ["builtin_provider_manifests"]
