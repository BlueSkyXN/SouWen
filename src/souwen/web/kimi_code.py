"""Kimi Code 搜索与网页获取 API 客户端。"""

from __future__ import annotations

import asyncio
import logging
import sys
from uuid import uuid4

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult, WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.kimi_code")


def _clamp_limit(value: int | float | str | None, default: int = 10) -> int:
    try:
        return max(1, min(int(value), 20))
    except (TypeError, ValueError):
        return default


def _positive_int(value: int | float | str | None, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _truncate(
    content: str,
    start_index: int = 0,
    max_length: int | None = None,
) -> tuple[str, bool, int | None]:
    start = max(0, int(start_index or 0))
    sliced = content[start:]
    if max_length is None:
        return sliced, False, None
    limit = max(0, int(max_length))
    if len(sliced) <= limit:
        return sliced, False, None
    return sliced[:limit], True, start + limit


class KimiCodeClient(SouWenHttpClient):
    """Kimi Code 搜索与网页获取客户端。

    该接口使用 Kimi Code API Key，不是 Moonshot/Kimi 开放平台 API Key。
    """

    ENGINE_NAME = "kimi_code"
    PROVIDER_NAME = "kimi_code"
    BASE_URL = "https://api.kimi.com"
    DEFAULT_SEARCH_PATH = "/coding/v1/search"
    DEFAULT_FETCH_PATH = "/coding/v1/fetch"

    def __init__(self, api_key: str | None = None) -> None:
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("kimi_code", "kimi_code_api_key")
        if not self.api_key:
            raise ConfigError(
                "kimi_code_api_key",
                "Kimi Code",
                "https://www.kimi.com/",
            )
        self._params = config.resolve_params("kimi_code")
        super().__init__(base_url=self.BASE_URL, source_name="kimi_code")

    def _endpoint(self, param_name: str, default_path: str) -> str:
        value = self._params.get(param_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return default_path

    def _headers(self, accept: str = "application/json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Msh-Platform": str(self._params.get("msh_platform") or "kimi_cli"),
            "X-Msh-Version": str(self._params.get("msh_version") or "test"),
            "X-Msh-Device-Name": str(self._params.get("msh_device_name") or "kimi-search-mcp"),
            "X-Msh-Device-Model": str(self._params.get("msh_device_model") or "kimi-search-mcp"),
            "X-Msh-Os-Version": str(self._params.get("msh_os_version") or sys.platform),
            "X-Msh-Device-Id": str(self._params.get("msh_device_id") or "kimi-search-mcp"),
            "X-Msh-Tool-Call-Id": f"souwen_{uuid4().hex}",
        }
        return headers

    async def search(
        self,
        query: str,
        max_results: int = 10,
        include_content: bool = False,
        timeout_seconds: int = 30,
    ) -> WebSearchResponse:
        """通过 Kimi Code 搜索 API 检索网页结果。"""

        timeout_value = _positive_int(timeout_seconds, 30)
        payload = {
            "text_query": query,
            "limit": _clamp_limit(max_results),
            "enable_page_crawling": bool(include_content),
            "timeout_seconds": timeout_value,
        }
        resp = await self.post(
            self._endpoint("search_url", self.DEFAULT_SEARCH_PATH),
            json=payload,
            headers=self._headers(),
        )
        try:
            data = resp.json()
        except Exception as exc:
            raise ParseError(f"Kimi Code 搜索响应解析失败: {exc}") from exc

        items = data.get("search_results") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ParseError("Kimi Code 搜索响应缺少 search_results 列表")

        results: list[WebSearchResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            title = str(item.get("title") or url).strip()
            snippet = str(item.get("snippet") or item.get("content") or "").strip()
            raw = {
                "provider": "kimi_code_search",
                "site_name": item.get("site_name"),
                "date": item.get("date"),
                "icon": item.get("icon"),
                "mime": item.get("mime"),
            }
            if item.get("content"):
                raw["content"] = item.get("content")
            results.append(
                WebSearchResult(
                    source=self.PROVIDER_NAME,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("Kimi Code 返回 %d 条结果 (query=%s)", len(results), query)
        return WebSearchResponse(
            query=query,
            source=self.PROVIDER_NAME,
            results=results,
            total_results=len(results),
        )

    async def fetch(
        self,
        url: str,
        timeout: float = 30.0,
        *,
        start_index: int = 0,
        max_length: int | None = None,
    ) -> FetchResult:
        """通过 Kimi Code fetch API 提取单个 URL 的 Markdown 内容。"""

        from souwen.web.fetch import validate_fetch_url

        valid, reason = validate_fetch_url(url)
        if not valid:
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=reason,
                raw={"provider": "kimi_code_fetch", "blocked_by_ssrf": True},
            )

        try:
            resp = await asyncio.wait_for(
                self.post(
                    self._endpoint("fetch_url", self.DEFAULT_FETCH_PATH),
                    json={"url": url},
                    headers=self._headers(accept="text/markdown"),
                ),
                timeout=timeout,
            )
            content, truncated, next_start = _truncate(resp.text, start_index, max_length)
            return FetchResult(
                url=url,
                final_url=url,
                content=content,
                content_format="markdown",
                content_truncated=truncated,
                next_start_index=next_start,
                source=self.PROVIDER_NAME,
                snippet=content[:500],
                raw={"provider": "kimi_code_fetch"},
            )
        except asyncio.TimeoutError:
            logger.warning("Kimi Code fetch timeout: url=%s timeout=%.1fs", url, timeout)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=f"Kimi Code fetch 超时 ({timeout:.0f}s)",
                raw={"provider": "kimi_code_fetch"},
            )
        except Exception as exc:
            logger.warning("Kimi Code fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "kimi_code_fetch"},
            )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = 3,
        timeout: float = 30.0,
        *,
        start_index: int = 0,
        max_length: int | None = None,
    ) -> FetchResponse:
        """批量提取 URL 内容。"""

        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(item: str) -> FetchResult:
            async with sem:
                return await self.fetch(
                    item,
                    timeout=timeout,
                    start_index=start_index,
                    max_length=max_length,
                )

        results = list(await asyncio.gather(*[_fetch_one(item) for item in urls]))
        ok = sum(1 for item in results if item.error is None)
        return FetchResponse(
            urls=urls,
            results=results,
            total=len(results),
            total_ok=ok,
            total_failed=len(results) - ok,
            provider=self.PROVIDER_NAME,
        )
