"""Search-only Provider v2 bridge for the existing LibriVox client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec.book_catalog import (
    BookCatalogBinding,
    BookCatalogSearchProvider,
)


class LibriVoxClientProtocol(Protocol):
    async def search(
        self, query: str, per_page: int = 10, page: int = 1, *, search_field: str = "title"
    ) -> Any: ...


class LibriVoxSearchProvider(BookCatalogSearchProvider):
    def __init__(self, client: LibriVoxClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(
            client,
            BookCatalogBinding("librivox", page_supported=True, max_limit=50),
            enabled=enabled,
        )


__all__ = ["LibriVoxClientProtocol", "LibriVoxSearchProvider"]
