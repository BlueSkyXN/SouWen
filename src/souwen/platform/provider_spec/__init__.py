"""Typed, static Provider v2 specifications and generic adapter helpers."""

from .factory import (
    LegacyFetchProvider,
    LegacyFetchSpec,
    LegacySearchProvider,
    LegacySearchSpec,
    RestJsonSearchProvider,
)
from .models import (
    LegacyFetchProviderSpec,
    LegacySearchProviderSpec,
    LegacyTransportDeclaration,
    ProviderSpec,
    RestJsonProviderSpec,
)
from .resolver import resolve_provider_inputs
from .validation import validate_spec_manifest

__all__ = [
    "LegacyFetchProvider",
    "LegacyFetchProviderSpec",
    "LegacyFetchSpec",
    "LegacySearchProvider",
    "LegacySearchProviderSpec",
    "LegacySearchSpec",
    "LegacyTransportDeclaration",
    "ProviderSpec",
    "RestJsonProviderSpec",
    "RestJsonSearchProvider",
    "resolve_provider_inputs",
    "validate_spec_manifest",
]
