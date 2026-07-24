"""Single-capability asynchronous provider ports."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from souwen.platform.provider_spi.dto import (
    FetchResult,
    FetchTargetRequest,
    LLMSearchRequest,
    LLMSearchResult,
    ProviderProbe,
    RequestContext,
    SearchPage,
    SearchRequest,
)
from souwen.platform.provider_spi.execution import ExecutionContext


@runtime_checkable
class SearchProvider(Protocol):
    """An adapter that implements only the ``search`` capability."""

    capability: Literal["search"]

    async def search(
        self, request: SearchRequest, context: RequestContext, execution: ExecutionContext
    ) -> SearchPage:
        """Return a canonical page or raise a typed ``ProviderError``."""

    async def probe(self, execution: ExecutionContext) -> ProviderProbe:
        """Perform one bounded, safe, explicitly requested probe."""

    async def close(self) -> None:
        """Release only owned resources; implementations must be idempotent."""


@runtime_checkable
class LLMSearchProvider(Protocol):
    """An adapter that implements only the ``llm_search`` capability."""

    capability: Literal["llm_search"]

    async def search(
        self, request: LLMSearchRequest, context: RequestContext, execution: ExecutionContext
    ) -> LLMSearchResult:
        """Return a canonical result or raise a typed ``ProviderError``."""

    async def probe(self, execution: ExecutionContext) -> ProviderProbe:
        """Perform one bounded, safe, explicitly requested probe."""

    async def close(self) -> None:
        """Release only owned resources; implementations must be idempotent."""


@runtime_checkable
class FetchProvider(Protocol):
    """An adapter that implements only the ``fetch`` capability."""

    capability: Literal["fetch"]

    async def fetch(
        self, request: FetchTargetRequest, context: RequestContext, execution: ExecutionContext
    ) -> FetchResult:
        """Return one canonical target result or raise a typed ``ProviderError``."""

    async def probe(self, execution: ExecutionContext) -> ProviderProbe:
        """Perform one bounded, safe, explicitly requested probe."""

    async def close(self) -> None:
        """Release only owned resources; implementations must be idempotent."""


__all__ = ["FetchProvider", "LLMSearchProvider", "SearchProvider"]
