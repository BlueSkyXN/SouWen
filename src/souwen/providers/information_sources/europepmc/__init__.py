"""Built-in Europe PMC Provider v2 package."""

from .adapter import EuropePmcClientProtocol, EuropePmcSearchProvider
from .manifest import EUROPEPMC_PROVIDER_MANIFEST
from .spec import EUROPEPMC_PROVIDER_SPEC

__all__ = [
    "EUROPEPMC_PROVIDER_MANIFEST",
    "EUROPEPMC_PROVIDER_SPEC",
    "EuropePmcClientProtocol",
    "EuropePmcSearchProvider",
]
