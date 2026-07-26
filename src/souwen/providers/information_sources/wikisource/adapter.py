"""Search-only Provider v2 bridge for the existing Wikisource client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec.book_catalog import (
    BookCatalogBinding,
    BookCatalogSearchProvider,
)


class WikisourceClientProtocol(Protocol):
    async def search(
        self, query: str, per_page: int = 10, page: int = 1, language: str = "zh"
    ) -> Any: ...


class WikisourceSearchProvider(BookCatalogSearchProvider):
    def __init__(self, client: WikisourceClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(
            client,
            BookCatalogBinding(
                "wikisource",
                page_supported=True,
                max_limit=20,
                fixed_search_kwargs=(("language", "zh"),),
            ),
            enabled=enabled,
        )


__all__ = ["WikisourceClientProtocol", "WikisourceSearchProvider"]
