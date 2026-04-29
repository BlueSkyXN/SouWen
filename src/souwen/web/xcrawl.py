"""XCrawl 搜索与抓取 API 客户端。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

from souwen.config import get_config
from souwen.exceptions import ConfigError, ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult, SourceType, WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.xcrawl")


class XCrawlClient(SouWenHttpClient):
    """XCrawl API 客户端。

    Args:
        api_key: XCrawl API Key，默认从 ``SOUWEN_XCRAWL_API_KEY`` 或频道配置读取。
    """

    ENGINE_NAME = "xcrawl"
    PROVIDER_NAME = "xcrawl"
    BASE_URL = "https://run.xcrawl.com"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("xcrawl", "xcrawl_api_key")
        if not self.api_key:
            raise ConfigError(
                "xcrawl_api_key",
                "XCrawl",
                "https://www.xcrawl.com/",
            )
        super().__init__(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            source_name="xcrawl",
        )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        location: str = "US",
        language: str = "en",
    ) -> WebSearchResponse:
        """通过 XCrawl Search API 检索网页结果。"""
        payload = {
            "query": query,
            "location": location,
            "language": language,
            "limit": max(1, min(int(max_results), 100)),
        }
        resp = await self.post("/v1/search", json=payload)
        try:
            data = resp.json()
        except Exception as exc:
            raise ParseError(f"XCrawl Search 响应解析失败: {exc}") from exc

        result_payload = data.get("data", {})
        if isinstance(result_payload, dict):
            items = result_payload.get("data") or result_payload.get("results") or []
        elif isinstance(result_payload, list):
            items = result_payload
            result_payload = {}
        else:
            items = []
            result_payload = {}

        results: list[WebSearchResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            title = str(item.get("title") or url).strip()
            snippet = str(
                item.get("description") or item.get("snippet") or item.get("content") or ""
            ).strip()
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_XCRAWL,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw={
                        "provider": "xcrawl_search",
                        "position": item.get("position"),
                        "search_id": data.get("search_id") or result_payload.get("search_id"),
                        "status": data.get("status") or result_payload.get("status"),
                        "credits_used": result_payload.get("credits_used"),
                    },
                )
            )

        logger.info("XCrawl 返回 %d 条结果 (query=%s)", len(results), query)
        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_XCRAWL,
            results=results,
            total_results=len(results),
        )

    async def scrape(
        self,
        url: str,
        timeout: float = 30.0,
        formats: list[str] | None = None,
        mode: Literal["sync", "async"] = "sync",
        proxy: dict[str, Any] | None = None,
        request: dict[str, Any] | None = None,
        js_render: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        webhook: dict[str, Any] | None = None,
    ) -> FetchResult:
        """通过 XCrawl Scrape API 抓取单个 URL。

        SouWen fetch provider 默认使用 ``mode="sync"``，直接返回页面内容。
        """
        del timeout  # 请求级 timeout 由 SouWenHttpClient 统一配置。
        payload = self._build_scrape_payload(
            url=url,
            formats=formats,
            mode=mode,
            proxy=proxy,
            request=request,
            js_render=js_render,
            output=output,
            webhook=webhook,
        )
        try:
            resp = await self.post("/v1/scrape", json=payload)
            try:
                data = resp.json()
            except Exception as exc:
                raise ParseError(f"XCrawl Scrape 响应解析失败: {exc}") from exc
            return self._scrape_response_to_fetch_result(url, data)
        except Exception as exc:
            logger.warning("XCrawl scrape failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "xcrawl_scrape"},
            )

    async def scrape_batch(
        self,
        urls: list[str],
        max_concurrency: int = 3,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL。"""
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(u: str) -> FetchResult:
            async with sem:
                return await self.scrape(u, timeout=timeout)

        results = list(await asyncio.gather(*[_fetch_one(u) for u in urls]))
        ok = sum(1 for result in results if result.error is None)
        return FetchResponse(
            urls=urls,
            results=results,
            total=len(results),
            total_ok=ok,
            total_failed=len(results) - ok,
            provider=self.PROVIDER_NAME,
        )

    async def get_scrape_result(self, scrape_id: str) -> dict[str, Any]:
        """查询异步 scrape 任务结果。"""
        resp = await self.get(f"/v1/scrape/{scrape_id}")
        try:
            data = resp.json()
        except Exception as exc:
            raise ParseError(f"XCrawl Scrape Result 响应解析失败: {exc}") from exc
        return data

    async def map(
        self,
        url: str,
        limit: int = 5000,
        filter: str | None = None,
        include_subdomains: bool = True,
        ignore_query_parameters: bool = True,
    ) -> dict[str, Any]:
        """通过 XCrawl Map API 获取站点 URL 列表。"""
        payload: dict[str, Any] = {
            "url": url,
            "limit": max(1, min(int(limit), 100000)),
            "include_subdomains": include_subdomains,
            "ignore_query_parameters": ignore_query_parameters,
        }
        if filter:
            payload["filter"] = filter
        resp = await self.post("/v1/map", json=payload)
        try:
            data = resp.json()
        except Exception as exc:
            raise ParseError(f"XCrawl Map 响应解析失败: {exc}") from exc
        return data

    async def crawl(
        self,
        url: str,
        limit: int = 100,
        max_depth: int = 3,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        include_entire_domain: bool = False,
        include_subdomains: bool = False,
        include_external_links: bool = False,
        sitemaps: bool = True,
        proxy: dict[str, Any] | None = None,
        request: dict[str, Any] | None = None,
        js_render: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        webhook: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """创建 XCrawl Crawl 异步爬取任务。"""
        crawler: dict[str, Any] = {
            "limit": max(1, int(limit)),
            "max_depth": max(0, int(max_depth)),
            "include_entire_domain": include_entire_domain,
            "include_subdomains": include_subdomains,
            "include_external_links": include_external_links,
            "sitemaps": sitemaps,
        }
        if include:
            crawler["include"] = include
        if exclude:
            crawler["exclude"] = exclude

        payload: dict[str, Any] = {"url": url, "crawler": crawler}
        if proxy:
            payload["proxy"] = proxy
        if request:
            payload["request"] = request
        if js_render:
            payload["js_render"] = js_render
        payload["output"] = output or {"formats": ["markdown"]}
        if webhook:
            payload["webhook"] = webhook

        resp = await self.post("/v1/crawl", json=payload)
        try:
            data = resp.json()
        except Exception as exc:
            raise ParseError(f"XCrawl Crawl 响应解析失败: {exc}") from exc
        return data

    async def get_crawl_result(self, crawl_id: str) -> dict[str, Any]:
        """查询 XCrawl Crawl 任务状态与结果。"""
        resp = await self.get(f"/v1/crawl/{crawl_id}")
        try:
            data = resp.json()
        except Exception as exc:
            raise ParseError(f"XCrawl Crawl Result 响应解析失败: {exc}") from exc
        return data

    @staticmethod
    def _build_scrape_payload(
        *,
        url: str,
        formats: list[str] | None,
        mode: Literal["sync", "async"],
        proxy: dict[str, Any] | None,
        request: dict[str, Any] | None,
        js_render: dict[str, Any] | None,
        output: dict[str, Any] | None,
        webhook: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "url": url,
            "mode": mode,
            "output": output or {"formats": formats or ["markdown"]},
        }
        if proxy:
            payload["proxy"] = proxy
        if request:
            payload["request"] = request
        if js_render:
            payload["js_render"] = js_render
        if webhook:
            payload["webhook"] = webhook
        return payload

    @classmethod
    def _scrape_response_to_fetch_result(
        cls, requested_url: str, data: dict[str, Any]
    ) -> FetchResult:
        status = str(data.get("status") or "")
        result_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        metadata = (
            result_data.get("metadata") if isinstance(result_data.get("metadata"), dict) else {}
        )

        content, content_format = cls._pick_content(result_data)
        final_url = (
            metadata.get("final_url")
            or metadata.get("sourceURL")
            or metadata.get("source_url")
            or metadata.get("url")
            or data.get("url")
            or requested_url
        )
        title = str(metadata.get("title") or "")
        description = str(metadata.get("description") or "").strip()
        snippet = description or (content[:500] if content else "")
        error = None
        if status and status != "completed":
            error = f"XCrawl scrape status={status}"
        elif not result_data:
            error = "XCrawl scrape response missing data"

        raw = {
            "provider": "xcrawl_scrape",
            "scrape_id": data.get("scrape_id"),
            "status": status,
            "credits_used": result_data.get("credits_used"),
            "credits_detail": result_data.get("credits_detail"),
            "metadata": metadata,
        }
        for key in ("links", "screenshot", "summary", "json"):
            if key in result_data:
                raw[key] = result_data[key]

        return FetchResult(
            url=requested_url,
            final_url=str(final_url),
            title=title,
            content=content,
            content_format=content_format,
            source=XCrawlClient.PROVIDER_NAME,
            snippet=snippet,
            error=error,
            raw=raw,
        )

    @staticmethod
    def _pick_content(data: dict[str, Any]) -> tuple[str, Literal["markdown", "text", "html"]]:
        for key, content_format in (
            ("markdown", "markdown"),
            ("summary", "markdown"),
            ("html", "html"),
            ("raw_html", "html"),
        ):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value, content_format  # type: ignore[return-value]
        json_value = data.get("json")
        if json_value:
            return json.dumps(json_value, ensure_ascii=False), "text"
        links = data.get("links")
        if isinstance(links, list) and links:
            return "\n".join(str(link) for link in links), "text"
        return "", "markdown"
