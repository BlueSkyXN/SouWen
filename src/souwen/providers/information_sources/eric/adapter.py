"""ERIC's thin generic REST JSON Provider v2 binding."""

from __future__ import annotations

from typing import Any, Protocol

from souwen.platform.provider_spec import RestJsonSearchProvider

from .spec import ERIC_REST_SPEC


class EricClientProtocol(Protocol):
    async def search(self, query: str, rows: int = 10, start: int = 0) -> Any: ...
    async def close(self) -> None: ...


class EricSearchProvider(RestJsonSearchProvider):
    def __init__(self, client: EricClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, ERIC_REST_SPEC, enabled=enabled)


__all__ = ["EricClientProtocol", "EricSearchProvider"]
