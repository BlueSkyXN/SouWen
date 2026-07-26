"""Provider v2 bridge for Xiaohongshu's DDG site-search client."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec import CnScraperBinding, CnScraperSearchProvider

_BINDING = CnScraperBinding("xiaohongshu", "cn_tech", result_host="xiaohongshu.com")


class XiaohongshuClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 20) -> Any: ...
    async def close(self) -> None: ...


class XiaohongshuSearchProvider(CnScraperSearchProvider):
    def __init__(self, client: XiaohongshuClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BINDING, enabled=enabled)


def create_xiaohongshu_client() -> Any:
    from souwen.providers.runtime_clients.web.xiaohongshu import XiaohongshuClient

    return XiaohongshuClient()


__all__ = ["XiaohongshuClientProtocol", "XiaohongshuSearchProvider", "create_xiaohongshu_client"]
