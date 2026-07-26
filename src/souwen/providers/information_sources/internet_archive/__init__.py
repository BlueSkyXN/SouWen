"""Built-in Internet Archive Provider v2 package."""

from .adapter import InternetArchiveClientProtocol, InternetArchiveSearchProvider
from .manifest import INTERNET_ARCHIVE_PROVIDER_MANIFEST
from .spec import INTERNET_ARCHIVE_PROVIDER_SPEC

__all__ = [
    "INTERNET_ARCHIVE_PROVIDER_MANIFEST",
    "INTERNET_ARCHIVE_PROVIDER_SPEC",
    "InternetArchiveClientProtocol",
    "InternetArchiveSearchProvider",
]
