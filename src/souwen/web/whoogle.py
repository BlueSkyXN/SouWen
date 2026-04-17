"""Client for Whoogle

Purpose:
    Google SERP self-hosted mirror

API Endpoint:
    Whoogle service

Key Features:
    - Privacy-focused Google search mirror, no tracking

Engine Class:
    WhoogleClient(SouWenHttpClient)
        async def search(query, max_results) -> WebSearchResponse

Returns:
    WebSearchResponse with title, url, snippet fields
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.whoogle")


class WhoogleClient(SouWenHttpClient):
    """Whoogle HTML 搜索客户端

    Args:
        instance_url: Whoogle 实例 URL (如 http://localhost:5000)
                     默认从 SOUWEN_WHOOGLE_URL 环境变量读取
    """

    ENGINE_NAME = "whoogle"

    def __init__(self, instance_url: str | None = None):
        config = get_config()
        self.instance_url = (
            instance_url or config.resolve_api_key("whoogle", "whoogle_url") or ""
        ).rstrip("/")
        if not self.instance_url:
            raise ConfigError(
                "whoogle_url",
                "Whoogle",
                "https://github.com/benbusby/whoogle-search",
            )
        super().__init__(base_url=self.instance_url, source_name="whoogle")

    async def search(
        self,
        query: str,
        max_results: int = 20,
    ) -> WebSearchResponse:
        """通过 Whoogle 搜索（HTML 解析）

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
        """
        params: dict[str, Any] = {"q": query}

        resp = await self.get("/search", params=params)
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Whoogle HTML 解析失败: {e}") from e

        results: list[WebSearchResult] = []
        try:
            containers = soup.select("div.ZINbbc") or soup.select("div.g")
            for container in containers:
                if len(results) >= max_results:
                    break

                # 提取标题
                title_tag = container.select_one("h3")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                if not title:
                    continue

                # 提取 URL
                link_tag = container.select_one("a")
                if not link_tag:
                    continue
                url = link_tag.get("href", "")
                if isinstance(url, list):
                    url = url[0] if url else ""
                url = str(url).strip()
                if not url.startswith("http"):
                    continue

                # 提取摘要
                snippet = ""
                snippet_tag = container.select_one(".BNeawe.s3v9rd")
                if not snippet_tag:
                    for tag in container.select("div.BNeawe"):
                        if tag != title_tag and "h3" not in [c.name for c in tag.parents]:
                            snippet = tag.get_text(strip=True)
                            break
                else:
                    snippet = snippet_tag.get_text(strip=True)

                results.append(
                    WebSearchResult(
                        source=SourceType.WEB_WHOOGLE,
                        title=title,
                        url=url,
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                    )
                )
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Whoogle 结果提取失败: {e}") from e

        logger.info("Whoogle 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_WHOOGLE,
            results=results,
            total_results=len(results),
        )
