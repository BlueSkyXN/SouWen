"""Reddit 搜索客户端

文件用途：
    Reddit 公开 JSON API 搜索客户端。通过在常规 Reddit URL 后追加 ``.json`` 后缀
    访问的非鉴权端点检索帖子，无需 API Key、OAuth 或登录。支持按相关性、热度、
    时间排序，并可按时间窗口过滤。返回归一化的 ``WebSearchResult`` 列表，
    permalink 自动拼接为完整 URL，selftext 截取前 300 字符作为 snippet。

函数/类清单：
    RedditClient（类）
        - 功能：Reddit 公开 JSON API 搜索客户端
        - 继承：SouWenHttpClient（HTTP 客户端基类，提供重试 / 代理 / 异常映射）
        - 关键属性：
            ENGINE_NAME = "reddit"
            BASE_URL = "https://www.reddit.com"
            SNIPPET_MAX_LEN = 300
            VALID_SORTS = {"relevance", "hot", "new", "top", "comments"}
            VALID_TIME_FILTERS = {"all", "hour", "day", "week", "month", "year"}
        - 主要方法：
            * search(query, max_results, sort, time_filter, restrict_sr) → WebSearchResponse

    RedditClient.__init__()
        - 功能：初始化 Reddit 客户端，设置自定义 User-Agent
        - 输入：无（公开 API，无 Key 参数）
        - 备注：Reddit 强制要求自定义 User-Agent，使用默认 UA 易触发 429。
            通过 ``source_name="reddit"`` 让 SouWenConfig 接管 base_url/proxy/headers
            的频道级覆盖。

    RedditClient.search(query, max_results=10, sort="relevance",
                        time_filter="all", restrict_sr=False) → WebSearchResponse
        - 功能：调用 GET /search.json 检索 Reddit 帖子
        - 输入：
            query (str) — 搜索关键词
            max_results (int) — 最大返回结果数（默认 10，Reddit 单页上限 100）
            sort (str) — 排序方式：relevance / hot / new / top / comments
            time_filter (str) — 时间窗口：all / hour / day / week / month / year
            restrict_sr (bool) — 是否仅在当前 subreddit 内搜索（默认 False）
        - 输出：WebSearchResponse 包含 WebSearchResult 列表
        - 异常：
            ValueError — sort / time_filter 不在允许集合中
            ParseError — Reddit 响应非 JSON 或结构异常
        - 字段映射：
            * source       = SourceType.WEB_REDDIT
            * title        = data["title"]
            * url          = "https://www.reddit.com" + data["permalink"]
            * snippet      = data["selftext"][:300]（自我帖子摘要）
            * engine       = "reddit"
            * raw          = { subreddit, score, num_comments, created_utc,
                               upvote_ratio, is_self, domain, author, ... }

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.exceptions: ParseError 异常
    - souwen.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - 端点必须带 .json 后缀，否则 Reddit 返回 HTML
    - permalink 字段不含域名（如 "/r/Python/comments/abc/title/"），需拼接前缀
    - selftext 仅在 self post（is_self=True）时非空，链接帖通常为空字符串
    - created_utc 是 Unix 时间戳浮点数，未做日期归一化（保留在 raw 中）
    - 公开 API 限流较严（约 60 req/min），调用方需酌情控制频率
    - User-Agent 必须独特且可识别，否则 Reddit 会持续返回 429
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.reddit")


class RedditClient(SouWenHttpClient):
    """Reddit 搜索客户端（公开 JSON API）

    通过 Reddit 的非鉴权 ``.json`` 端点检索帖子，无需 API Key 或 OAuth。
    Reddit 要求所有请求携带自定义 User-Agent，否则会被频繁限流（429）。

    Example:
        async with RedditClient() as c:
            resp = await c.search("python asyncio", max_results=20, sort="top",
                                  time_filter="month")
            for r in resp.results:
                print(r.title, r.url)
    """

    ENGINE_NAME = "reddit"
    BASE_URL = "https://www.reddit.com"

    SNIPPET_MAX_LEN = 300

    VALID_SORTS = frozenset({"relevance", "hot", "new", "top", "comments"})
    VALID_TIME_FILTERS = frozenset(
        {"all", "hour", "day", "week", "month", "year"}
    )

    def __init__(self):
        # Reddit 强制要求自定义 User-Agent；使用 SouWen 标识 + 仓库 URL 便于追溯
        super().__init__(
            base_url=self.BASE_URL,
            headers={
                "User-Agent": (
                    "SouWen/1.0 (Academic & Patent Search Tool; "
                    "+https://github.com/BlueSkyXN/SouWen)"
                ),
                "Accept": "application/json",
            },
            source_name="reddit",
        )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        sort: str = "relevance",
        time_filter: str = "all",
        restrict_sr: bool = False,
    ) -> WebSearchResponse:
        """通过 Reddit 公开 JSON API 搜索帖子

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（默认 10，Reddit 单页上限 100）
            sort: 排序方式 - relevance / hot / new / top / comments
            time_filter: 时间窗口 - all / hour / day / week / month / year
            restrict_sr: 是否仅在当前 subreddit 内搜索

        Returns:
            WebSearchResponse 包含归一化后的搜索结果

        Raises:
            ValueError: sort / time_filter 不在允许集合中
            ParseError: Reddit 响应非 JSON 或结构异常
        """
        if sort not in self.VALID_SORTS:
            raise ValueError(
                f"无效的 sort: {sort!r}，可选值: {sorted(self.VALID_SORTS)}"
            )
        if time_filter not in self.VALID_TIME_FILTERS:
            raise ValueError(
                f"无效的 time_filter: {time_filter!r}，"
                f"可选值: {sorted(self.VALID_TIME_FILTERS)}"
            )

        # Reddit 单页上限 100；下限 1 防止请求被拒
        limit = max(1, min(max_results, 100))

        params: dict[str, Any] = {
            "q": query,
            "sort": sort,
            "limit": limit,
            "t": time_filter,
            "restrict_sr": "true" if restrict_sr else "false",
            # raw_json=1 让 Reddit 返回未 HTML 转义的字段（&amp; → &）
            "raw_json": 1,
        }

        # 端点必须带 .json 后缀，否则返回 HTML
        resp = await self.get("/search.json", params=params)

        try:
            data = resp.json()
        except Exception as e:
            raise ParseError(f"Reddit 响应解析失败: {e}") from e

        children = (data.get("data") or {}).get("children") or []

        results: list[WebSearchResult] = []
        for child in children:
            post = child.get("data") if isinstance(child, dict) else None
            if not isinstance(post, dict):
                continue

            title = (post.get("title") or "").strip()
            permalink = post.get("permalink") or ""
            if not title or not permalink:
                # 缺标题或链接的不完整记录直接跳过
                continue

            # permalink 不含域名（如 "/r/Python/comments/abc/title/"），需拼前缀
            url = f"{self.BASE_URL}{permalink}"

            # selftext 仅 self post 非空；截断防止 snippet 过长
            selftext = (post.get("selftext") or "").strip()
            snippet = selftext[: self.SNIPPET_MAX_LEN]

            # 收集 Reddit 特有元数据，便于上层 Agent 进一步分析
            raw: dict[str, Any] = {
                "subreddit": post.get("subreddit"),
                "score": post.get("score"),
                "num_comments": post.get("num_comments"),
                "created_utc": post.get("created_utc"),
                "upvote_ratio": post.get("upvote_ratio"),
                "is_self": post.get("is_self"),
                "domain": post.get("domain"),
                "author": post.get("author"),
                "permalink": permalink,
                # 链接类帖子的外链目标（非 self post）
                "external_url": post.get("url") if not post.get("is_self") else None,
            }

            results.append(
                WebSearchResult(
                    source=SourceType.WEB_REDDIT,
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
            "Reddit 返回 %d 条结果 (query=%s, sort=%s, t=%s)",
            len(results),
            query,
            sort,
            time_filter,
        )

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_REDDIT,
            results=results,
            total_results=len(results),
        )
