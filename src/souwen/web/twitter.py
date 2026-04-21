"""Twitter/X API v2 搜索客户端

文件用途：
    Twitter/X 官方 API v2 搜索客户端。使用 Bearer Token（OAuth 2.0 App-Only）
    调用 ``GET /2/tweets/search/recent`` 检索最近 7 天的推文，将结果归一化为
    统一 ``WebSearchResult`` 模型。需要有效的 Bearer Token（Twitter/X Developer
    Portal 申请，Basic 及以上套餐才支持搜索接口）。

函数/类清单：
    TwitterClient（类）
        - 功能：Twitter/X API v2 推文搜索客户端
        - 继承：SouWenHttpClient（HTTP 客户端基类，提供重试 / 代理 / 异常映射）
        - 关键属性：
            ENGINE_NAME = "twitter"
            BASE_URL = "https://api.twitter.com"
            SNIPPET_MAX_LEN = 280（推文字符上限）
            VALID_SORT_ORDERS = {"recency", "relevancy"}
        - 主要方法：
            * search(query, max_results, sort_order, start_time, end_time) → WebSearchResponse

    TwitterClient.__init__(bearer_token=None)
        - 功能：初始化 Twitter 客户端，配置 Bearer Token 鉴权头
        - 输入：bearer_token (str|None) — 从参数 / SOUWEN_TWITTER_BEARER_TOKEN
                环境变量 / config.twitter_bearer_token 读取；未配置时抛 ConfigError
        - 异常：ConfigError — Bearer Token 未配置时抛出，调度层应捕获并跳过

    TwitterClient.search(query, max_results=10, sort_order="recency",
                         start_time=None, end_time=None) → WebSearchResponse
        - 功能：调用 GET /2/tweets/search/recent 搜索最近 7 天推文
        - 输入：
            query (str) — 搜索关键词，支持 Twitter 搜索算子
                          (如 ``"python lang:en -is:retweet"``）
            max_results (int) — 最大返回结果数（API 范围 10–100）
            sort_order (str) — 排序：recency（时间倒序）/ relevancy（相关性）
            start_time (str|None) — ISO 8601 开始时间（如 "2024-01-01T00:00:00Z"）
            end_time (str|None) — ISO 8601 结束时间
        - 输出：WebSearchResponse 包含 WebSearchResult 列表
        - 异常：
            ValueError — sort_order 不在允许集合中，或 max_results 超出范围
            ParseError — API 响应非 JSON 或结构异常
        - 字段映射：
            * source       = SourceType.WEB_TWITTER
            * title        = tweet["text"][:100] + "…"（截断前 100 字符作标题）
            * url          = "https://x.com/{username}/status/{tweet_id}"
            * snippet      = tweet["text"]（完整推文内容）
            * engine       = "twitter"
            * published_date = tweet["created_at"]（ISO 8601）
            * raw          = { tweet_id, author_id, username, name,
                               retweet_count, reply_count, like_count,
                               quote_count, impression_count, lang,
                               created_at, conversation_id }

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: get_config 读取配置
    - souwen.exceptions: ConfigError, ParseError 异常
    - souwen.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：GET https://api.twitter.com/2/tweets/search/recent
    - 鉴权：Authorization: Bearer <bearer_token>（OAuth 2.0 App-Only）
    - max_results 范围：10–100（API 强制要求，低于 10 会返回 400）
    - tweet.fields：text, created_at, author_id, public_metrics, lang, conversation_id
    - expansions：author_id 以获取用户名和显示名
    - 用户信息通过 includes.users 映射，以 author_id 为 key 关联推文
    - 速率限制：Basic 套餐 60 req/15min；Free 套餐不支持搜索（返回 403）
    - 文档：https://developer.twitter.com/en/docs/twitter-api/tweets/search/api-reference/get-tweets-search-recent
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError, ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.twitter")


class TwitterClient(SouWenHttpClient):
    """Twitter/X API v2 推文搜索客户端

    通过官方 API v2 的 ``/2/tweets/search/recent`` 端点检索最近 7 天的推文。
    需要有效的 Bearer Token；Free 套餐不包含搜索访问权限，至少需要 Basic 套餐。

    Example:
        async with TwitterClient() as c:
            resp = await c.search("python asyncio -is:retweet lang:en",
                                  max_results=20, sort_order="recency")
            for r in resp.results:
                print(r.title, r.url)
    """

    ENGINE_NAME = "twitter"
    BASE_URL = "https://api.twitter.com"

    SNIPPET_MAX_LEN = 280  # 推文最大字符数

    VALID_SORT_ORDERS = frozenset({"recency", "relevancy"})

    def __init__(self, bearer_token: str | None = None):
        """初始化 Twitter/X 搜索客户端

        Args:
            bearer_token: Twitter/X Bearer Token，默认从
                          ``SOUWEN_TWITTER_BEARER_TOKEN`` 环境变量或
                          config.twitter_bearer_token 读取；未配置则抛
                          ``ConfigError``，调度层应捕获并跳过本源。
        """
        config = get_config()
        self._bearer_token = (
            bearer_token
            or config.resolve_api_key("twitter", "twitter_bearer_token")
        )
        if not self._bearer_token:
            raise ConfigError(
                "twitter_bearer_token",
                "Twitter/X",
                "https://developer.twitter.com/en/portal/dashboard",
            )

        super().__init__(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self._bearer_token}",
                "Accept": "application/json",
            },
            source_name="twitter",
        )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        sort_order: str = "recency",
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> WebSearchResponse:
        """通过 Twitter/X API v2 搜索最近 7 天的推文

        Args:
            query: 搜索关键词，支持 Twitter 搜索算子，
                   例如 ``"python lang:en -is:retweet"``
            max_results: 最大返回结果数（API 强制范围 10–100）
            sort_order: 排序方式 — ``recency``（时间倒序）/ ``relevancy``（相关性）
            start_time: ISO 8601 开始时间（如 ``"2024-01-01T00:00:00Z"``），
                        仅检索此时间之后的推文（最远 7 天前）
            end_time: ISO 8601 结束时间

        Returns:
            WebSearchResponse 包含归一化后的推文搜索结果

        Raises:
            ValueError: sort_order 不合法，或 max_results 超出 API 限制
            ParseError: API 响应非 JSON 或结构异常
        """
        if sort_order not in self.VALID_SORT_ORDERS:
            raise ValueError(
                f"无效的 sort_order: {sort_order!r}，"
                f"可选值: {sorted(self.VALID_SORT_ORDERS)}"
            )

        # Twitter API 强制 max_results 在 10–100 之间
        capped = max(10, min(max_results, 100))
        if capped != max_results and max_results < 10:
            logger.debug("max_results=%d 低于 API 下限 10，自动调整为 10", max_results)

        params: dict[str, Any] = {
            "query": query,
            "max_results": capped,
            "sort_order": sort_order,
            # 请求推文详情字段
            "tweet.fields": "created_at,author_id,text,public_metrics,lang,conversation_id",
            # 通过 expansions 关联用户信息（用户名、显示名）
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        resp = await self.get("/2/tweets/search/recent", params=params)

        try:
            data = resp.json()
        except Exception as e:
            raise ParseError(f"Twitter API 响应解析失败: {e}") from e

        # 构建 author_id → {username, name} 映射表
        users: dict[str, dict[str, str]] = {}
        for user in (data.get("includes") or {}).get("users") or []:
            uid = user.get("id")
            if uid:
                users[uid] = {
                    "username": user.get("username") or "",
                    "name": user.get("name") or "",
                }

        tweets = data.get("data") or []
        results: list[WebSearchResult] = []

        for tweet in tweets:
            if len(results) >= max_results:
                break

            tweet_id = tweet.get("id") or ""
            text = (tweet.get("text") or "").strip()
            author_id = tweet.get("author_id") or ""
            if not tweet_id or not text:
                continue

            user_info = users.get(author_id, {})
            username = user_info.get("username") or author_id

            # 推文 URL：x.com/{username}/status/{tweet_id}
            url = f"https://x.com/{username}/status/{tweet_id}"

            # 标题取推文前 100 字符，超出追加省略号
            title = text if len(text) <= 100 else text[:100] + "…"

            # 收集公开互动指标
            metrics = tweet.get("public_metrics") or {}
            raw: dict[str, Any] = {
                "tweet_id": tweet_id,
                "author_id": author_id,
                "username": username,
                "name": user_info.get("name"),
                "retweet_count": metrics.get("retweet_count"),
                "reply_count": metrics.get("reply_count"),
                "like_count": metrics.get("like_count"),
                "quote_count": metrics.get("quote_count"),
                "impression_count": metrics.get("impression_count"),
                "lang": tweet.get("lang"),
                "created_at": tweet.get("created_at"),
                "conversation_id": tweet.get("conversation_id"),
            }

            results.append(
                WebSearchResult(
                    source=SourceType.WEB_TWITTER,
                    title=title,
                    url=url,
                    snippet=text[: self.SNIPPET_MAX_LEN],
                    engine=self.ENGINE_NAME,
                    published_date=tweet.get("created_at"),
                    raw=raw,
                )
            )

        meta = data.get("meta") or {}
        total = meta.get("result_count", len(results))
        logger.info(
            "Twitter 返回 %d 条结果 (query=%s, sort=%s)",
            len(results),
            query,
            sort_order,
        )

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_TWITTER,
            results=results,
            total_results=total,
        )
