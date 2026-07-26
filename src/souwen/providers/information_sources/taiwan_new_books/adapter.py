"""Search-only Provider v2 bridge for the local Taiwan new-books catalog client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec.book_catalog import (
    BookCatalogBinding,
    BookCatalogSearchProvider,
)


class TaiwanNewBooksClientProtocol(Protocol):
    async def search(self, query: str, per_page: int = 10) -> Any: ...


class TaiwanNewBooksSearchProvider(BookCatalogSearchProvider):
    def __init__(self, client: TaiwanNewBooksClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(
            client, BookCatalogBinding("taiwan_new_books", page_supported=False), enabled=enabled
        )


__all__ = ["TaiwanNewBooksClientProtocol", "TaiwanNewBooksSearchProvider"]
