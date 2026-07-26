"""Provider v2 bridge for V2EX's DDG site-search client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec import CnScraperBinding, CnScraperSearchProvider

_BINDING = CnScraperBinding("v2ex", "cn_tech", result_host="v2ex.com")


class V2EXClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 20) -> Any: ...
    async def close(self) -> None: ...


class V2EXSearchProvider(CnScraperSearchProvider):
    def __init__(self, client: V2EXClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BINDING, enabled=enabled)


def create_v2ex_client() -> Any:
    from souwen.web.v2ex import V2EXClient

    return V2EXClient()


__all__ = ["V2EXClientProtocol", "V2EXSearchProvider", "create_v2ex_client"]
