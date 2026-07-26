"""Provider v2 bridge for CSDN anonymous article search."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec import CnScraperBinding, CnScraperSearchProvider

_BINDING = CnScraperBinding("csdn", "cn_tech")


class CSDNClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 20) -> Any: ...
    async def close(self) -> None: ...


class CSDNSearchProvider(CnScraperSearchProvider):
    def __init__(self, client: CSDNClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BINDING, enabled=enabled)


def create_csdn_client() -> Any:
    from souwen.web.csdn import CSDNClient

    return CSDNClient(follow_redirects=False)


__all__ = ["CSDNClientProtocol", "CSDNSearchProvider", "create_csdn_client"]
