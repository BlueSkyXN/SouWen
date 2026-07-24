"""Manifest registry boundary. Owner: Platform. Allowed dependencies: contracts and Platform metadata only."""

from .models import AdapterDeclaration, ProviderManifest
from .registry import ManifestDiagnostic, ManifestRegistration, ManifestRegistry

__all__ = [
    "AdapterDeclaration",
    "ManifestDiagnostic",
    "ManifestRegistration",
    "ManifestRegistry",
    "ProviderManifest",
]
