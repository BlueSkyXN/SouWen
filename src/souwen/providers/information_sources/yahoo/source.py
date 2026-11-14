"""Yahoo 搜索源（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

新增一个源 = 新增一个这样的模块和它的夹具/测试；源目录之外没有按
源 id 的业务分派。``server.v2_runtime`` 按目录发现 ``source.py``。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote_plus, unquote

from bs4 import BeautifulSoup

from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from souwen.common_runtime.provider_support.scraper.base import BaseScraper
from souwen.config import SouWenConfig
from souwen.platform.manifest_registry import ProviderManifest
from souwen.platform.provider_spec import (
    HttpOperation,
    ScraperSearchProvider,
    client_scraper_spec,
    scraper_search_manifest,
)
from souwen.providers.runtime_clients.models import WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.providers.information_sources.yahoo")

# ---------------------------------------------------------------------------
# 声明（identity）：manifest + spec
# ---------------------------------------------------------------------------

MANIFEST: ProviderManifest = scraper_search_manifest(
    "yahoo", "YahooSearchProvider", ["search.yahoo.com"]
)
SPEC = client_scraper_spec(
    "yahoo", "web", "search.yahoo.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)


# ---------------------------------------------------------------------------
# 请求构造 + HTML 解析（transport client）
# ---------------------------------------------------------------------------


class YahooClient(BaseScraper):
    """Yahoo 搜索客户端（Bing 供给；对数据中心 IP 较宽容）。"""

    ENGINE_NAME = "yahoo"
    BASE_URL = "https://search.yahoo.com/search"

    def __init__(self, **kwargs):
        super().__init__(min_delay=1.5, max_delay=4.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        url = f"{self._resolved_base_url}?p={quote_plus(query)}"
        resp = await self._fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")
        results: list[WebSearchResult] = []
        try:
            for element in soup.select(".algo"):
                title_el = element.select_one("h3")
                if title_el is None:
                    continue
                title = title_el.get_text(strip=True)
                link_el = element.select_one(".compTitle a")
                raw_url = link_el.get("href", "") if link_el else ""
                snippet_el = element.select_one(".compText")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                real_url = self._decode_yahoo_url(str(raw_url))
                if not real_url or not real_url.startswith(("http://", "https://")):
                    continue
                if title:
                    results.append(
                        WebSearchResult(
                            source="yahoo",
                            title=title,
                            url=real_url,
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )
                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Yahoo HTML 解析失败: %s", e)
        logger.info("Yahoo 返回 %d 条结果 (query=%s)", len(results), query)
        return WebSearchResponse(
            query=query, source="yahoo", results=results, total_results=len(results)
        )

    @staticmethod
    def _decode_yahoo_url(url: str) -> str:
        """解码 Yahoo 重定向（RU=ENCODED/RK=...）。"""
        if "RU=" in url and "/RK=" in url:
            start = url.find("RU=") + 3
            sub = url[start:]
            end = sub.find("/RK=")
            if end != -1:
                try:
                    return unquote(sub[:end])
                except (ValueError, UnicodeDecodeError):
                    pass
        return url


# ---------------------------------------------------------------------------
# Provider 桥 + 注册入口
# ---------------------------------------------------------------------------


class YahooSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="yahoo", domain="web", enabled=enabled)


PROVIDER_TYPE = YahooSearchProvider


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets
    from souwen.server.v2_runtime import _RuntimeClientAdapter

    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        client = YahooClient(follow_redirects=False)
    return YahooSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


__all__ = [
    "MANIFEST",
    "PROVIDER_TYPE",
    "SPEC",
    "YahooClient",
    "YahooSearchProvider",
    "build_provider",
]
