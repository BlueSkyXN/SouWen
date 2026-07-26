"""Built-in DataCite Provider v2 package."""

from .adapter import DataCiteClientProtocol, DataCiteSearchProvider
from .manifest import DATACITE_PROVIDER_MANIFEST
from .spec import DATACITE_PROVIDER_SPEC

__all__ = [
    "DATACITE_PROVIDER_MANIFEST",
    "DATACITE_PROVIDER_SPEC",
    "DataCiteClientProtocol",
    "DataCiteSearchProvider",
]
