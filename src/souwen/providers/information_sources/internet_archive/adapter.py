"""Search-only Provider v2 bridge for the existing Internet Archive client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec.book_catalog import (
    BookCatalogBinding,
    BookCatalogSearchProvider,
)


class InternetArchiveClientProtocol(Protocol):
    async def search(self, query: str, per_page: int = 10, page: int = 1) -> Any: ...


class InternetArchiveSearchProvider(BookCatalogSearchProvider):
    def __init__(self, client: InternetArchiveClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(
            client, BookCatalogBinding("internet_archive", page_supported=True), enabled=enabled
        )


__all__ = ["InternetArchiveClientProtocol", "InternetArchiveSearchProvider"]
