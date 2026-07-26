"""Provider v2 bridge for bounded Weibo mobile search."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec import CnScraperBinding, CnScraperSearchProvider

_BINDING = CnScraperBinding("weibo", "social", max_limit=10, result_host="m.weibo.cn")


class WeiboClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...
    async def close(self) -> None: ...


class WeiboSearchProvider(CnScraperSearchProvider):
    def __init__(self, client: WeiboClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BINDING, enabled=enabled)


def create_weibo_client() -> Any:
    from souwen.web.weibo import WeiboClient

    return WeiboClient(follow_redirects=False)


__all__ = ["WeiboClientProtocol", "WeiboSearchProvider", "create_weibo_client"]
