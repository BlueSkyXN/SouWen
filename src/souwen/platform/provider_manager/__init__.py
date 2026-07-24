"""Provider assembly boundary. Owner: Platform. Allowed dependencies: SPI, manifest registry, and provider factories."""

from .manager import FactoryRegistration, ProviderDiagnostic, ProviderManager, ProviderManagerError

__all__ = [
    "FactoryRegistration",
    "ProviderDiagnostic",
    "ProviderManager",
    "ProviderManagerError",
]
