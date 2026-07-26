"""Search-only Provider v2 bridge for the legacy DOAB client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec.book_catalog import (
    BookCatalogBinding,
    BookCatalogSearchProvider,
)


class DOABClientProtocol(Protocol):
    async def search(self, query: str, per_page: int = 10, page: int = 1) -> Any: ...


class DOABSearchProvider(BookCatalogSearchProvider):
    def __init__(self, client: DOABClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(
            client,
            BookCatalogBinding("doab", page_supported=True, max_limit=25),
            enabled=enabled,
        )


__all__ = ["DOABClientProtocol", "DOABSearchProvider"]
