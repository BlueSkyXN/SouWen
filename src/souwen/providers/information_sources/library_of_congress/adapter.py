"""Search-only Provider v2 bridge for the existing Library of Congress client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec.book_catalog import (
    BookCatalogBinding,
    BookCatalogSearchProvider,
)


class LibraryOfCongressClientProtocol(Protocol):
    async def search(self, query: str, per_page: int = 10, page: int = 1) -> Any: ...


class LibraryOfCongressSearchProvider(BookCatalogSearchProvider):
    def __init__(self, client: LibraryOfCongressClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(
            client, BookCatalogBinding("library_of_congress", page_supported=True), enabled=enabled
        )


__all__ = ["LibraryOfCongressClientProtocol", "LibraryOfCongressSearchProvider"]
