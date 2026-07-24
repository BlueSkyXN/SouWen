"""LLM Search public API. Owner: LLM Search Core. Allowed dependencies: Provider SPI only."""

from __future__ import annotations

from typing import Protocol

from souwen.modules.llm_search.application import LLMSearchModuleService
from souwen.platform.provider_spi import (
    ExecutionContext,
    LLMSearchRequest,
    LLMSearchResult,
    RequestContext,
)


class LLMSearchModule(Protocol):
    """Public asynchronous entry port for canonical LLM Search."""

    async def search(
        self, request: LLMSearchRequest, context: RequestContext, execution: ExecutionContext
    ) -> LLMSearchResult:
        """Execute LLM Search without exposing a concrete provider."""


__all__ = [
    "LLMSearchModule",
    "LLMSearchModuleService",
    "LLMSearchRequest",
    "LLMSearchResult",
]
