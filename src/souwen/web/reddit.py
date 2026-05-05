"""Reddit 搜索客户端

文件用途：
    Reddit 搜索客户端，支持两种模式：
      1. **官方 OAuth2 模式**（推荐）：提供 client_id + client_secret 后，通过
         client_credentials 流程获取 Bearer Token，调用 ``oauth.reddit.com/search``
         官方端点。速率 100 QPM，遵循 Reddit API 服务条款。
      2. **公开 JSON 模式**（兜底）：不提供凭据时，通过在 Reddit URL 后追加
         ``.json`` 后缀访问非鉴权公开端点，无需注册，速率约 60 req/min。

    两种模式返回相同的归一化 ``WebSearchResult`` 列表，接口完全兼容。

函数/类清单：
    RedditClient（类）
        - 功能：Reddit 搜索客户端，自动选择 OAuth2 或公开 JSON 模式
        - 继承：SouWenHttpClient（HTTP 客户端基类，提供重试 / 代理 / 异常映射）
        - 关键属性：
            ENGINE_NAME = "reddit"
            BASE_URL = "https://www.reddit.com"
            OAUTH_BASE_URL = "https://oauth.reddit.com"
            SNIPPET_MAX_LEN = 300
            VALID_SORTS = {"relevance", "hot", "new", "top", "comments"}
            VALID_TIME_FILTERS = {"all", "hour", "day", "week", "month", "year"}
        - 主要方法：
            * search(query, max_results, sort, time_filter, restrict_sr) → WebSearchResponse

    RedditClient.__init__(client_id=None, client_secret=None)
        - 功能：初始化 Reddit 客户端，自动检测是否启用 OAuth2 模式
        - 输入：
            client_id (str|None) — Reddit 应用 Client ID，
                从参数 / SOUWEN_REDDIT_CLIENT_ID / config.reddit_client_id 读取；
                不提供则降级为公开 JSON 模式
            client_secret (str|None) — Reddit 应用 Client Secret，
                从参数 / SOUWEN_REDDIT_CLIENT_SECRET / config.reddit_client_secret 读取
        - 备注：Reddit 强制要求自定义 User-Agent，官方 API 文档要求格式为
            ``<platform>:<app_id>:<version> (by /u/<username>)``

    RedditClient.search(query, max_results=10, sort="relevance",
                        time_filter="all", restrict_sr=False) → WebSearchResponse
        - 功能：搜索 Reddit 帖子
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
                               upvote_ratio, is_self, domain, author,
                               oauth_mode（是否使用 OAuth2 模式）, ... }

模块依赖：
    - base64: Basic Auth 编码（OAuth2 token 请求）
    - logging: 日志记录
    - time: token 过期计算
    - typing: 类型注解
    - souwen.config: get_config 读取配置
    - souwen.core.exceptions: ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - OAuth2 token 端点：POST https://www.reddit.com/api/v1/access_token
      * grant_type=client_credentials（无需用户登录）
      * Basic Auth：base64(client_id:client_secret)
    - OAuth2 搜索端点：GET https://oauth.reddit.com/search
    - 公开 JSON 搜索端点：GET https://www.reddit.com/search.json（须带 .json 后缀）
    - token 有效期 3600s，内置缓存自动刷新
    - permalink 字段不含域名（"/r/Python/comments/abc/title/"），需拼接前缀
    - selftext 仅在 self post（is_self=True）时非空，链接帖通常为空字符串
    - created_utc 是 Unix 时间戳浮点数，未做日期归一化（保留在 raw 中）
    - User-Agent 必须独特且可识别，否则 Reddit 会持续返回 429
    - 注册 Reddit 应用（官方 OAuth）：https://www.reddit.com/prefs/apps
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import AuthError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.reddit")

_USER_AGENT = "SouWen/1.0 (Academic & Patent Search Tool; +https://github.com/BlueSkyXN/SouWen)"


class RedditClient(SouWenHttpClient):
    """Reddit 搜索客户端（支持官方 OAuth2 模式和公开 JSON 模式）

    优先使用官方 OAuth2（提供 client_id + client_secret 时），未配置凭据时
    自动降级为公开 JSON API，两种模式接口完全兼容。

    OAuth2 模式优点：
      - 遵循 Reddit 官方 API 服务条款
      - 速率 100 QPM，高于公开 API 的 ~60 req/min
      - 支持更丰富的查询参数和高级功能

    Example（OAuth2 模式）：
        async with RedditClient(client_id="xxx", client_secret="yyy") as c:
            resp = await c.search("python asyncio", max_results=20, sort="top")
            for r in resp.results:
                print(r.title, r.url)

    Example（公开 JSON 模式，无需凭据）：
        async with RedditClient() as c:
            resp = await c.search("machine learning", time_filter="week")
    """

    ENGINE_NAME = "reddit"
    BASE_URL = "https://www.reddit.com"
    OAUTH_BASE_URL = "https://oauth.reddit.com"
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

    SNIPPET_MAX_LEN = 300

    VALID_SORTS = frozenset({"relevance", "hot", "new", "top", "comments"})
    VALID_TIME_FILTERS = frozenset({"all", "hour", "day", "week", "month", "year"})

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        """初始化 Reddit 客户端

        Args:
            client_id: Reddit App Client ID，从参数 /
                       ``SOUWEN_REDDIT_CLIENT_ID`` 环境变量 /
                       config.reddit_client_id 读取；
                       不提供时降级为公开 JSON 模式。
            client_secret: Reddit App Client Secret，从参数 /
                           ``SOUWEN_REDDIT_CLIENT_SECRET`` 环境变量 /
                           config.reddit_client_secret 读取。
        """
        config = get_config()
        self._client_id = client_id or config.resolve_api_key("reddit", "reddit_client_id")
        self._client_secret = client_secret or config.resolve_api_key(
            "reddit", "reddit_client_secret"
        )

        # 是否启用官方 OAuth2 模式
        self._oauth_mode = bool(self._client_id and self._client_secret)
        if self._oauth_mode:
            logger.debug("Reddit 客户端使用官方 OAuth2 模式（client_id 已配置）")
        else:
            logger.debug("Reddit 客户端使用公开 JSON 模式（未配置 OAuth2 凭据）")

        # OAuth2 token 缓存
        self._oauth_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock: asyncio.Lock = asyncio.Lock()

        super().__init__(
            base_url=self.BASE_URL,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
            },
            source_name="reddit",
        )

    async def _get_oauth_token(self) -> str:
        """获取或刷新 OAuth2 Bearer Token（client_credentials 流程）

        Token 有效期 3600s，提前 60s 视为过期并主动刷新。
        使用 asyncio.Lock 防止并发请求重复获取 Token。

        Returns:
            有效的 Bearer Token 字符串

        Raises:
            ParseError: token 端点返回非 JSON 或 access_token 字段缺失
        """
        async with self._token_lock:
            now = time.monotonic()
            if self._oauth_token and now < self._token_expires_at:
                return self._oauth_token

            # Basic Auth：base64(client_id:client_secret)
            credentials = f"{self._client_id}:{self._client_secret}"
            encoded = base64.b64encode(credentials.encode()).decode()

            resp = await self.post(
                self.TOKEN_URL,
                data={"grant_type": "client_credentials"},
                headers={
                    "Authorization": f"Basic {encoded}",
                    "User-Agent": _USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            try:
                token_data = resp.json()
            except Exception as e:
                raise ParseError(f"Reddit OAuth2 token 解析失败: {e}") from e

            access_token = token_data.get("access_token")
            if not access_token:
                raise ParseError(f"Reddit OAuth2 未返回 access_token: {token_data}")

            expires_in = token_data.get("expires_in", 3600)
            # 提前 60s 过期，防止边界情况
            self._token_expires_at = time.monotonic() + float(expires_in) - 60.0
            self._oauth_token = access_token
            logger.debug("Reddit OAuth2 token 已刷新，有效期 %ds", expires_in)
            return access_token

    async def search(
        self,
        query: str,
        max_results: int = 10,
        sort: str = "relevance",
        time_filter: str = "all",
        restrict_sr: bool = False,
    ) -> WebSearchResponse:
        """搜索 Reddit 帖子

        根据是否配置了 OAuth2 凭据，自动选择官方 API 或公开 JSON 端点。

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
            raise ValueError(f"无效的 sort: {sort!r}，可选值: {sorted(self.VALID_SORTS)}")
        if time_filter not in self.VALID_TIME_FILTERS:
            raise ValueError(
                f"无效的 time_filter: {time_filter!r}，可选值: {sorted(self.VALID_TIME_FILTERS)}"
            )

        # Reddit 单页上限 100；下限 1 防止请求被拒
        limit = max(1, min(max_results, 100))

        params: dict[str, Any] = {
            "q": query,
            "sort": sort,
            "limit": limit,
            "t": time_filter,
            "restrict_sr": "true" if restrict_sr else "false",
            "raw_json": 1,
        }

        if self._oauth_mode:
            # 官方 OAuth2 端点（oauth.reddit.com/search）
            token = await self._get_oauth_token()
            try:
                resp = await self.get(
                    f"{self.OAUTH_BASE_URL}/search",
                    params=params,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "User-Agent": _USER_AGENT,
                    },
                )
            except AuthError:
                # Token 可能被提前撤销，清除缓存后重试一次
                self._oauth_token = None
                self._token_expires_at = 0.0
                token = await self._get_oauth_token()
                resp = await self.get(
                    f"{self.OAUTH_BASE_URL}/search",
                    params=params,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "User-Agent": _USER_AGENT,
                    },
                )
        else:
            # 公开 JSON 端点（www.reddit.com/search.json）
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
                continue

            # permalink 不含域名，需拼接前缀
            url = f"{self.BASE_URL}{permalink}"

            # selftext 仅 self post 非空；截断防止 snippet 过长
            selftext = (post.get("selftext") or "").strip()
            snippet = selftext[: self.SNIPPET_MAX_LEN]

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
                "external_url": post.get("url") if not post.get("is_self") else None,
                "oauth_mode": self._oauth_mode,
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

        mode_label = "OAuth2" if self._oauth_mode else "公开 JSON"
        logger.info(
            "Reddit [%s] 返回 %d 条结果 (query=%s, sort=%s, t=%s)",
            mode_label,
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
