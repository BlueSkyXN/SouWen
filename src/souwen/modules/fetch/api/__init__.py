"""Fetch public API. Owner: Fetch Core. Allowed dependencies: Provider SPI only."""

from __future__ import annotations

from typing import Protocol

from souwen.platform.provider_spi import ExecutionContext, FetchBatch, FetchRequest, RequestContext


class FetchModule(Protocol):
    """Public asynchronous entry port for the canonical Fetch use case."""

    async def fetch(
        self, request: FetchRequest, context: RequestContext, execution: ExecutionContext
    ) -> FetchBatch:
        """Execute Fetch without exposing a concrete provider."""


__all__ = ["FetchBatch", "FetchModule", "FetchRequest"]
