"""Wikipedia 百科搜索客户端"""

from __future__ import annotations

import html
import logging
import re
from typing import Any
from urllib.parse import quote

from souwen.common_runtime.provider_support.exceptions import ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.providers.runtime_clients.models import WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.providers.runtime_clients.web.wikipedia")

# 匹配任意 HTML 标签（非贪婪），用于剥离 MediaWiki snippet 高亮标签
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# 折叠多余空白（含 &nbsp; 解码后产生的不可见字符）
_WS_RE = re.compile(r"\s+")


def _clean_html(text: str) -> str:
    """剥离 MediaWiki snippet 中的 HTML 标签并解码实体。

    MediaWiki 返回的 snippet 形如：
        '...这是<span class="searchmatch">关键词</span>所在的句子...'
    本函数去除标签、解码 ``&amp;`` 等实体、折叠空白，输出干净文本。
    """
    if not text:
        return ""
    no_tag = _HTML_TAG_RE.sub("", text)
    decoded = html.unescape(no_tag)
    return _WS_RE.sub(" ", decoded).strip()


class WikipediaClient(SouWenHttpClient):
    """Wikipedia 搜索客户端（MediaWiki Action API）

    通过维基百科公开的 ``action=query&list=search`` 接口检索条目，
    无需任何 API Key 或登录。支持按语言切换子站点（zh / en / ja / ...）。

    Example:
        async with WikipediaClient(lang="zh") as c:
            resp = await c.search("人工智能", max_results=5)
            for r in resp.results:
                print(r.title, r.url)

        # 临时切换到英文站
        async with WikipediaClient() as c:
            resp = await c.search("Quantum computing", lang="en")
    """

    ENGINE_NAME = "wikipedia"
    BASE_URL = "https://zh.wikipedia.org"
    API_PATH = "/w/api.php"
    # MediaWiki 普通用户 srlimit 上限
    MAX_LIMIT = 50

    def __init__(self, lang: str = "zh"):
        # 维基媒体 API 礼仪：必须自定义带项目身份的 User-Agent
        base_url = f"https://{lang}.wikipedia.org"
        super().__init__(
            base_url=base_url,
            headers={
                "User-Agent": (
                    "SouWen/1.0 (Academic & Patent Search Tool; "
                    "+https://github.com/BlueSkyXN/SouWen)"
                ),
                "Accept": "application/json",
            },
            source_name="wikipedia",
        )
        self._lang = lang

    async def search(
        self,
        query: str,
        max_results: int = 10,
        lang: str | None = None,
    ) -> WebSearchResponse:
        """通过 MediaWiki Action API 搜索维基百科条目。

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（默认 10，MediaWiki 单页上限 50）
            lang: 临时覆盖语言子站点（None 表示沿用实例 ``__init__`` 时的 lang）

        Returns:
            WebSearchResponse 包含归一化后的搜索结果

        Raises:
            ParseError: MediaWiki 响应非 JSON 或缺少 query.search 结构
        """
        # 单次调用允许临时覆盖 lang，便于复用同一个 client 跨语言查询
        effective_lang = lang or self._lang

        # MediaWiki srlimit 上限 50；下限 1 防止请求被拒
        limit = max(1, min(max_results, self.MAX_LIMIT))

        params: dict[str, Any] = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
            # 显式声明所需字段，避免依赖 MediaWiki 默认值漂移
            "srprop": "snippet|titlesnippet|timestamp|wordcount|size",
            # 让 MediaWiki 直接返回 utf-8，不做 \u 转义
            "utf8": 1,
        }

        # 当 lang 临时覆盖且与实例不同，需指向对应子站点的完整 URL；
        # 否则使用相对路径让 httpx 拼接实例 base_url
        if lang and lang != self._lang:
            target = f"https://{effective_lang}.wikipedia.org{self.API_PATH}"
        else:
            target = self.API_PATH

        resp = await self.get(target, params=params)

        try:
            data = resp.json()
        except Exception as e:
            raise ParseError(f"Wikipedia 响应解析失败: {e}") from e

        # MediaWiki 错误响应形如 {"error": {"code": ..., "info": ...}}
        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            info = err.get("info") if isinstance(err, dict) else str(err)
            raise ParseError(f"Wikipedia API 错误: {info}")

        try:
            search_items = data["query"]["search"]
        except (KeyError, TypeError) as e:
            raise ParseError(f"Wikipedia 响应缺少 query.search 字段: {data!r}") from e

        if not isinstance(search_items, list):
            raise ParseError(f"Wikipedia query.search 不是列表: {type(search_items).__name__}")

        results: list[WebSearchResult] = []
        for item in search_items:
            if not isinstance(item, dict):
                continue

            title = (item.get("title") or "").strip()
            if not title:
                # 缺标题的不完整记录直接跳过
                continue

            # 维基条目 URL 命名约定：空格 → 下划线，再做 percent-encoding；
            # 保留 ``:`` ``/`` 等维基命名空间分隔符
            url_title = quote(title.replace(" ", "_"), safe=":/()")
            url = f"https://{effective_lang}.wikipedia.org/wiki/{url_title}"

            snippet = _clean_html(item.get("snippet", ""))

            raw: dict[str, Any] = {
                "pageid": item.get("pageid"),
                "wordcount": item.get("wordcount"),
                "size": item.get("size"),
                "timestamp": item.get("timestamp"),
                "titlesnippet": item.get("titlesnippet"),
                "lang": effective_lang,
            }

            results.append(
                WebSearchResult(
                    source="wikipedia",
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

            if len(results) >= max_results:
                break

        logger.info(
            "Wikipedia 返回 %d 条结果 (query=%s, lang=%s)",
            len(results),
            query,
            effective_lang,
        )

        return WebSearchResponse(
            query=query,
            source="wikipedia",
            results=results,
            total_results=len(results),
        )
