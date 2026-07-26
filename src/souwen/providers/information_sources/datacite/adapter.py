"""Provider v2 Search bridge for anonymous DataCite research-output metadata."""

from __future__ import annotations

from typing import Any, Protocol

from souwen.platform.provider_spec.research_output import (
    ResearchOutputSearchProvider,
)


class DataCiteClientProtocol(Protocol):
    async def search(self, query: str, per_page: int = 10, page: int = 1) -> Any: ...
    async def close(self) -> None: ...


class DataCiteSearchProvider(ResearchOutputSearchProvider):
    def __init__(self, client: DataCiteClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, provider_id="datacite", limit_keyword="per_page", enabled=enabled)


__all__ = ["DataCiteClientProtocol", "DataCiteSearchProvider"]
