from .adapter import NewspaperClientProtocol, NewspaperFetchProvider
from .manifest import NEWSPAPER_PROVIDER_MANIFEST
from .spec import NEWSPAPER_FETCH_PROFILE

__all__ = [
    "NEWSPAPER_FETCH_PROFILE",
    "NEWSPAPER_PROVIDER_MANIFEST",
    "NewspaperClientProtocol",
    "NewspaperFetchProvider",
]
