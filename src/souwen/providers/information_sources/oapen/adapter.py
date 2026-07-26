"""Search-only Provider v2 bridge for the legacy OAPEN client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec.book_catalog import (
    BookCatalogBinding,
    BookCatalogSearchProvider,
)


class OAPENClientProtocol(Protocol):
    async def search(self, query: str, per_page: int = 10, page: int = 1) -> Any: ...


class OAPENSearchProvider(BookCatalogSearchProvider):
    def __init__(self, client: OAPENClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(
            client,
            BookCatalogBinding("oapen", page_supported=True, max_limit=25),
            enabled=enabled,
        )


__all__ = ["OAPENClientProtocol", "OAPENSearchProvider"]
