"""Provider v2 bridge for NodeSeek's DDG site-search client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec import CnScraperBinding, CnScraperSearchProvider

_BINDING = CnScraperBinding("nodeseek", "cn_tech", result_host="nodeseek.com")


class NodeSeekClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 20) -> Any: ...
    async def close(self) -> None: ...


class NodeSeekSearchProvider(CnScraperSearchProvider):
    def __init__(self, client: NodeSeekClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BINDING, enabled=enabled)


def create_nodeseek_client() -> Any:
    from souwen.providers.runtime_clients.web.nodeseek import NodeSeekClient

    return NodeSeekClient()


__all__ = ["NodeSeekClientProtocol", "NodeSeekSearchProvider", "create_nodeseek_client"]
