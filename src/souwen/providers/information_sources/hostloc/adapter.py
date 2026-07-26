"""Provider v2 bridge for HostLoc's DDG site-search client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec import CnScraperBinding, CnScraperSearchProvider

_BINDING = CnScraperBinding("hostloc", "cn_tech", result_host="hostloc.com")


class HostLocClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 20) -> Any: ...
    async def close(self) -> None: ...


class HostLocSearchProvider(CnScraperSearchProvider):
    def __init__(self, client: HostLocClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BINDING, enabled=enabled)


def create_hostloc_client() -> Any:
    from souwen.web.hostloc import HostLocClient

    return HostLocClient()


__all__ = ["HostLocClientProtocol", "HostLocSearchProvider", "create_hostloc_client"]
