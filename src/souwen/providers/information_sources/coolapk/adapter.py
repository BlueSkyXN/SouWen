"""Provider v2 bridge for Coolapk's DDG site-search client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec import CnScraperBinding, CnScraperSearchProvider

_BINDING = CnScraperBinding("coolapk", "cn_tech", result_host="coolapk.com")


class CoolapkClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 20) -> Any: ...
    async def close(self) -> None: ...


class CoolapkSearchProvider(CnScraperSearchProvider):
    def __init__(self, client: CoolapkClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BINDING, enabled=enabled)


def create_coolapk_client() -> Any:
    from souwen.providers.runtime_clients.web.coolapk import CoolapkClient

    return CoolapkClient()


__all__ = ["CoolapkClientProtocol", "CoolapkSearchProvider", "create_coolapk_client"]
