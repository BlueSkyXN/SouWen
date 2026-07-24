"""Transactional in-memory registry for validated static manifest declarations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .models import AdapterDeclaration, ProviderManifest


SAFE_REASON_CODES = frozenset(
    {
        "manifest_invalid",
        "duplicate_package",
        "duplicate_adapter",
    }
)


@dataclass(frozen=True, slots=True)
class ManifestDiagnostic:
    """A bounded diagnostic that deliberately excludes validation details."""

    reason_code: str
    package_id: str | None = None
    adapter_id: str | None = None


@dataclass(frozen=True, slots=True)
class ManifestRegistration:
    """The result of a static declaration registration attempt."""

    manifest: ProviderManifest | None
    diagnostic: ManifestDiagnostic | None

    @property
    def accepted(self) -> bool:
        return self.manifest is not None


class ManifestRegistry:
    """Store validated metadata without importing or constructing providers."""

    def __init__(self) -> None:
        self._packages: dict[str, ProviderManifest] = {}
        self._adapters: dict[str, tuple[str, AdapterDeclaration]] = {}
        self._diagnostics: list[ManifestDiagnostic] = []

    def register(self, declaration: ProviderManifest | Mapping[str, Any]) -> ManifestRegistration:
        """Validate then atomically add one package, quarantining only a new failure."""
        raw_package_id = _safe_package_id(declaration)
        try:
            manifest = (
                declaration
                if isinstance(declaration, ProviderManifest)
                else ProviderManifest.model_validate(declaration)
            )
        except (TypeError, ValidationError):
            return self._quarantine("manifest_invalid", package_id=raw_package_id)

        if manifest.id in self._packages:
            return self._quarantine("duplicate_package", package_id=manifest.id)

        duplicate = next(
            (adapter for adapter in manifest.adapters if adapter.id in self._adapters), None
        )
        if duplicate is not None:
            return self._quarantine(
                "duplicate_adapter",
                package_id=manifest.id,
                adapter_id=duplicate.id,
            )

        # Every duplicate check ran before either index is mutated.
        self._packages[manifest.id] = manifest
        for adapter in manifest.adapters:
            self._adapters[adapter.id] = (manifest.id, adapter)
        return ManifestRegistration(manifest=manifest, diagnostic=None)

    def discover(
        self, declarations: Iterable[ProviderManifest | Mapping[str, Any]]
    ) -> tuple[ManifestRegistration, ...]:
        """Register each supplied declaration independently and without loading code."""
        return tuple(self.register(declaration) for declaration in declarations)

    def package(self, package_id: str) -> ProviderManifest | None:
        """Return a registered package declaration by stable package ID."""
        return self._packages.get(package_id)

    def adapter(self, adapter_id: str) -> tuple[ProviderManifest, AdapterDeclaration] | None:
        """Return a static adapter declaration and its owning package."""
        item = self._adapters.get(adapter_id)
        if item is None:
            return None
        package_id, adapter = item
        return self._packages[package_id], adapter

    @property
    def packages(self) -> tuple[ProviderManifest, ...]:
        return tuple(self._packages.values())

    @property
    def diagnostics(self) -> tuple[ManifestDiagnostic, ...]:
        return tuple(self._diagnostics)

    def _quarantine(
        self,
        reason_code: str,
        *,
        package_id: str | None = None,
        adapter_id: str | None = None,
    ) -> ManifestRegistration:
        if reason_code not in SAFE_REASON_CODES:
            raise ValueError("unsupported manifest diagnostic code")
        diagnostic = ManifestDiagnostic(reason_code, package_id, adapter_id)
        self._diagnostics.append(diagnostic)
        return ManifestRegistration(manifest=None, diagnostic=diagnostic)


def _safe_package_id(declaration: ProviderManifest | Mapping[str, Any]) -> str | None:
    """Retain only an identifier that already satisfies the manifest ID shape."""
    candidate = (
        declaration.id if isinstance(declaration, ProviderManifest) else declaration.get("id")
    )
    if isinstance(candidate, str) and 0 < len(candidate) <= 128:
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789_-"
        if candidate[0] in "abcdefghijklmnopqrstuvwxyz" and all(
            char in alphabet for char in candidate
        ):
            return candidate
    return None
