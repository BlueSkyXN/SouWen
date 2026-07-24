"""Search public API. Owner: Search Core. Allowed dependencies: Search application and Provider SPI."""

from __future__ import annotations

from typing import Protocol

from souwen.modules.search.application import SearchModuleService
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchPage, SearchRequest


class SearchModule(Protocol):
    """Public asynchronous entry port for the canonical Search use case."""

    async def search(
        self, request: SearchRequest, context: RequestContext, execution: ExecutionContext
    ) -> SearchPage:
        """Execute Search without exposing a concrete provider."""


__all__ = ["SearchModule", "SearchModuleService", "SearchPage", "SearchRequest"]
