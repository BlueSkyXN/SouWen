"""Provider v2 bridge for Juejin anonymous article search."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec import CnScraperBinding, CnScraperSearchProvider

_BINDING = CnScraperBinding("juejin", "cn_tech", result_host="juejin.cn")


class JuejinClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 20) -> Any: ...
    async def close(self) -> None: ...


class JuejinSearchProvider(CnScraperSearchProvider):
    def __init__(self, client: JuejinClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BINDING, enabled=enabled)


def create_juejin_client() -> Any:
    from souwen.providers.runtime_clients.web.juejin import JuejinClient

    return JuejinClient(follow_redirects=False)


__all__ = ["JuejinClientProtocol", "JuejinSearchProvider", "create_juejin_client"]
