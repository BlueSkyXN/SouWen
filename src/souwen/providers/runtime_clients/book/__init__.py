"""Book-domain clients and normalized catalog APIs."""

from souwen.providers.runtime_clients.book.open_library import OpenLibraryClient
from souwen.providers.runtime_clients.book.internet_archive import InternetArchiveClient
from souwen.providers.runtime_clients.book.wikisource import WikisourceClient
from souwen.providers.runtime_clients.book.library_of_congress import LibraryOfCongressClient
from souwen.providers.runtime_clients.book.librivox import LibriVoxClient
from souwen.providers.runtime_clients.book.doab import DOABClient
from souwen.providers.runtime_clients.book.oapen import OAPENClient

__all__ = [
    "InternetArchiveClient",
    "DOABClient",
    "LibraryOfCongressClient",
    "LibriVoxClient",
    "OpenLibraryClient",
    "OAPENClient",
    "WikisourceClient",
]
