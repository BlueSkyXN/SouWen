"""Provider v2 bridge for bounded Zhihu public search."""

from __future__ import annotations
from typing import Any, Protocol
from souwen.platform.provider_spec import CnScraperBinding, CnScraperSearchProvider

_BINDING = CnScraperBinding("zhihu", "social", max_limit=20)


class ZhihuClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...
    async def close(self) -> None: ...


class ZhihuSearchProvider(CnScraperSearchProvider):
    def __init__(self, client: ZhihuClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BINDING, enabled=enabled)


def create_zhihu_client() -> Any:
    from souwen.web.zhihu import ZhihuClient

    return ZhihuClient(follow_redirects=False)


__all__ = ["ZhihuClientProtocol", "ZhihuSearchProvider", "create_zhihu_client"]
