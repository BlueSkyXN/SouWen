"""Wikipedia 百科搜索客户端

文件用途：
    Wikipedia（维基百科）MediaWiki Action API 搜索客户端，完全公开、无需任何
    认证或 API Key。通过 ``action=query&list=search`` 端点检索条目，支持多语言
    站点（zh / en / ja / ...）。返回归一化的 ``WebSearchResult`` 列表，
    snippet 中的 MediaWiki HTML 高亮标签（``<span class="searchmatch">`` 等）
    会被清理为纯文本，url 自动按维基条目命名约定（空格 → 下划线 + URL 编码）
    拼接为完整地址。

函数/类清单：
    WikipediaClient（类）
        - 功能：MediaWiki Action API 搜索客户端
        - 继承：SouWenHttpClient（HTTP 客户端基类，提供重试 / 代理 / 异常映射）
        - 关键属性：
            ENGINE_NAME = "wikipedia"
            BASE_URL    = "https://zh.wikipedia.org"   # 默认中文维基
            API_PATH    = "/w/api.php"
            MAX_LIMIT   = 50                           # MediaWiki srlimit 上限
        - 主要方法：
            * search(query, max_results, lang) → WebSearchResponse

    WikipediaClient.__init__(lang="zh")
        - 功能：初始化 Wikipedia 客户端，按 lang 选择语言子站点
        - 输入：
            lang (str) — 维基百科语言子域名（默认 "zh"，可选 "en"/"ja"/...）
        - 备注：
            - base_url 由 lang 拼接而成（``https://{lang}.wikipedia.org``）
            - User-Agent 必须自定义并带可识别身份，符合维基媒体 API 礼仪
            - source_name="wikipedia" 让 SouWenConfig 接管 base_url/proxy/headers
              的频道级覆盖

    WikipediaClient.search(query, max_results=10, lang=None) → WebSearchResponse
        - 功能：调用 GET /w/api.php 检索维基百科条目
        - 输入：
            query (str)         — 搜索关键词
            max_results (int)   — 最大返回结果数（默认 10，MediaWiki 单页上限 50）
            lang (str | None)   — 单次调用临时覆盖语言（不修改实例默认值）
        - 输出：WebSearchResponse 包含 WebSearchResult 列表
        - 异常：
            ParseError — MediaWiki 响应非 JSON 或缺少 query.search 结构
        - 字段映射：
            * source  = 'wikipedia'
            * title   = item["title"]
            * url     = "https://{lang}.wikipedia.org/wiki/" +
                        quote(title.replace(" ", "_"))
            * snippet = _clean_html(item["snippet"])
            * engine  = "wikipedia"
            * raw     = { pageid, wordcount, timestamp, size, ... }

    _clean_html(text)
        - 功能：去除 MediaWiki snippet 中的 HTML 标签并解码 HTML 实体
        - 输入：含 ``<span class="searchmatch">`` 等标签的字符串
        - 输出：折叠空白后的纯文本

模块依赖：
    - html / re: HTML 实体解码与标签剥离
    - logging: 日志记录
    - urllib.parse.quote: 维基条目名 URL 编码
    - typing: 类型注解
    - souwen.core.exceptions: ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: str, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - MediaWiki 默认返回 srprop=snippet|titlesnippet|timestamp|wordcount，
      其中 snippet 含 ``<span class="searchmatch">关键词</span>`` 高亮，
      必须剥离后才能作为干净的摘要展示
    - 条目 URL 命名约定：空格替换为下划线，再做 URL percent-encoding，
      其中 ``/`` / ``:`` 等字符在维基地址中应保留
    - 多语言支持：每个 lang 对应独立子域名（如 ja.wikipedia.org），url 必须
      与请求的 lang 一致，否则点开会进入错误的语言版本
    - 维基媒体 API 礼仪：必须自定义 User-Agent 并附带项目联系方式，
      否则可能被 WMF 限流或屏蔽
    - srlimit 上限为 50（普通用户）；超过时 MediaWiki 会忽略并使用上限值
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any
from urllib.parse import quote

from souwen.core.exceptions import ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.wikipedia")

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
