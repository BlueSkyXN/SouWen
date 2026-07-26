from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from souwen.platform.provider_spi import ProviderError, ProviderErrorCode
from souwen.platform.provider_spec import ScraperSearchProvider
from souwen.providers.runtime_clients.web.bilibili import BilibiliClient

_VIDEO_PATH = re.compile(r"^/video/(BV[0-9A-Za-z]+)$")


class BilibiliSearchProvider(ScraperSearchProvider):
    def __init__(self, client: Any, *, enabled: bool = True) -> None:
        super().__init__(client, provider_id="bilibili", domain="videos", enabled=enabled)

    async def search(self, request, context, execution):
        if request.page is not None and request.page.limit > 50:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, provider_id="bilibili")
        page = await super().search(request, context, execution)
        for item in page.items:
            parsed = urlsplit(str(item.url))
            if (
                parsed.scheme != "https"
                or parsed.hostname != "www.bilibili.com"
                or not _VIDEO_PATH.fullmatch(parsed.path)
            ):
                raise ProviderError(
                    ProviderErrorCode.INVALID_UPSTREAM_RESPONSE, provider_id="bilibili"
                )
        return page


def build_bilibili_client(_configuration: Any, secrets: dict[str, str]) -> BilibiliClient:
    """Construct the video-only bridge without consulting global credential config."""
    return BilibiliClient(sessdata=secrets.get("BILIBILI_SESSDATA"), follow_redirects=False)
