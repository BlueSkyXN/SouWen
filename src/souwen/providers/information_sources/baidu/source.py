"""baidu（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import logging
from bs4 import BeautifulSoup
from collections.abc import Mapping
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from souwen.common_runtime.provider_support.scraper.base import BaseScraper
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import HttpOperation, client_scraper_spec, ScraperSearchProvider
from souwen.providers.runtime_clients.models import WebSearchResult, WebSearchResponse
from typing import Any
from urllib.parse import quote_plus


from souwen.platform.provider_spec import scraper_search_manifest

BAIDU_PROVIDER_MANIFEST = scraper_search_manifest(
    "baidu",
    "BaiduSearchProvider",
    ["www.baidu.com"],
    max_egress="browser",
)


BAIDU_PROVIDER_SPEC = client_scraper_spec(
    "baidu", "web", "www.baidu.com", "html", (HttpOperation(method="GET", endpoint="/s"),)
)


logger = logging.getLogger("souwen.providers.runtime_clients.web.baidu")


class BaiduClient(BaseScraper):
    """Baidu 搜索客户端

    百度搜索引擎，中文搜索首选。
    通过 CSS 选择器解析搜索结果。
    注意：百度使用重定向 URL，直接使用 href 值。
    """

    ENGINE_NAME = "baidu"
    BASE_URL = "https://www.baidu.com/s"

    def __init__(self, **kwargs):
        # 初始化爬虫配置：最小延迟 1.0s、最大延迟 3.0s、最多重试 3 次
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Baidu

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        url = f"{self._resolved_base_url}?wd={quote_plus(query)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            # 遍历百度搜索结果的容器元素 div.c-container[id]
            for element in soup.select("div.c-container[id]"):
                # 提取标题和链接。标题在 .t > a 或 h3.t a
                title_el = element.select_one(".t > a") or element.select_one("h3.t a")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)
                # 百度使用重定向 URL，直接使用 href
                raw_url = title_el.get("href", "")

                # 提取 snippet（描述文本），尝试多个选择器
                snippet = ""
                snippet_el = element.select_one(".c-abstract")
                if snippet_el is None:
                    snippet_el = element.select_one(".c-span-last")
                if snippet_el is None:
                    snippet_el = element.select_one("p")
                if snippet_el:
                    snippet = snippet_el.get_text(strip=True)

                if not title:
                    continue

                results.append(
                    WebSearchResult(
                        source="baidu",
                        title=title,
                        url=str(raw_url),
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                    )
                )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Baidu HTML 解析失败: %s", e)

        logger.info("Baidu 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="baidu",
            results=results,
            total_results=len(results),
        )


class BaiduSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="baidu", domain="web", enabled=enabled)


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    from souwen.server.v2_runtime import _RuntimeClientAdapter

    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        client = BaiduClient(follow_redirects=False)
    return BaiduSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = BAIDU_PROVIDER_MANIFEST
SPEC = BAIDU_PROVIDER_SPEC
PROVIDER_TYPE = BaiduSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
