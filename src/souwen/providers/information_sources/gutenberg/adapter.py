"""Search-only Provider v2 bridge for the local Gutenberg catalog client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec.book_catalog import (
    BookCatalogBinding,
    BookCatalogSearchProvider,
)


class GutenbergClientProtocol(Protocol):
    async def search(self, query: str, per_page: int = 10) -> Any: ...


class GutenbergSearchProvider(BookCatalogSearchProvider):
    def __init__(self, client: GutenbergClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(
            client, BookCatalogBinding("gutenberg", page_supported=False), enabled=enabled
        )


__all__ = ["GutenbergClientProtocol", "GutenbergSearchProvider"]
