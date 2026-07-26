"""Search-only Provider v2 bridge for the existing Open Library client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec.book_catalog import (
    BookCatalogBinding,
    BookCatalogSearchProvider,
)


class OpenLibraryClientProtocol(Protocol):
    async def search(self, query: str, per_page: int = 10, page: int = 1) -> Any: ...


class OpenLibrarySearchProvider(BookCatalogSearchProvider):
    def __init__(self, client: OpenLibraryClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(
            client, BookCatalogBinding("open_library", page_supported=True), enabled=enabled
        )


__all__ = ["OpenLibraryClientProtocol", "OpenLibrarySearchProvider"]
