"""Provider v2 Search bridge for anonymous Figshare article metadata."""

from __future__ import annotations

from typing import Any, Protocol

from souwen.platform.provider_spec.research_output import (
    ResearchOutputSearchProvider,
)


class FigshareClientProtocol(Protocol):
    async def search(self, query: str, page_size: int = 10, page: int = 1) -> Any: ...
    async def close(self) -> None: ...


class FigshareSearchProvider(ResearchOutputSearchProvider):
    def __init__(self, client: FigshareClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, provider_id="figshare", limit_keyword="page_size", enabled=enabled)


__all__ = ["FigshareClientProtocol", "FigshareSearchProvider"]
