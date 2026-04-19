"""YouTube 视频搜索客户端

文件用途：
    YouTube Data API v3 搜索客户端。通过 Google 提供的公开 API 检索
    YouTube 视频内容。需要 API Key（通过配置字段 youtube_api_key
    或环境变量 YOUTUBE_API_KEY 提供），无 Key 时客户端初始化会抛出
    ConfigError 以便调度层（integration_type=official_api）跳过该数据源。

函数/类清单：
    resolve_api_key(legacy_field, env_var) -> str | None
        - 功能：解析 YouTube API Key，依次查询频道配置 / 旧版字段 / 环境变量
        - 输入：legacy_field 配置字段名，env_var 环境变量名
        - 输出：找到的 Key 字符串；都未配置时返回 None
        - 备注：作为模块级函数暴露，便于单元测试通过 monkeypatch 替换

    YouTubeClient（类）
        - 功能：YouTube Data API v3 视频搜索客户端
        - 继承：SouWenHttpClient（HTTP 客户端基类，提供重试 / 代理 / 异常映射）
        - 关键属性：
            ENGINE_NAME = "youtube"
            BASE_URL = "https://www.googleapis.com"
            SNIPPET_MAX_LEN = 300
            VALID_ORDERS = {"relevance", "date", "rating", "viewCount", "title"}
            VALID_VIDEO_TYPES = {"any", "episode", "movie"}
        - 主要方法：
            * search(query, max_results, order, video_type) → WebSearchResponse

    YouTubeClient.__init__()
        - 功能：初始化 YouTube 客户端
        - 输入：无（API Key 通过 resolve_api_key 解析）
        - 异常：ConfigError 当未配置 youtube_api_key 时抛出，方便上层跳过

    YouTubeClient.search(query, max_results=10, order="relevance",
                         video_type=None) → WebSearchResponse
        - 功能：调用 GET /youtube/v3/search 检索视频
        - 输入：
            query (str) — 搜索关键词
            max_results (int) — 最大返回结果数（API 单页上限 50）
            order (str) — 排序方式：relevance / date / rating / viewCount / title
            video_type (str|None) — 视频类型：any / episode / movie
        - 输出：WebSearchResponse 包含 WebSearchResult 列表
        - 异常：
            ValueError — order / video_type 不在允许集合中
            ParseError — YouTube 响应非 JSON 或结构异常
        - 字段映射：
            * source  = SourceType.WEB_YOUTUBE
            * title   = item["snippet"]["title"]
            * url     = "https://www.youtube.com/watch?v={item['id']['videoId']}"
            * snippet = item["snippet"]["description"][:300]
            * engine  = "youtube"
            * raw     = { channelTitle, channelId, publishedAt, thumbnails }

模块依赖：
    - logging: 日志记录
    - os: 读取环境变量回退路径
    - typing: 类型注解
    - souwen.config: get_config 获取全局配置
    - souwen.exceptions: ConfigError, ParseError 异常
    - souwen.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - 端点：GET https://www.googleapis.com/youtube/v3/search
    - 鉴权：通过 query string 参数 ``key={api_key}`` 传递（YouTube Data API 标准）
    - 单次返回上限 50，超出会被自动截断
    - type=video 限定仅返回视频结果，避免混入频道 / 播放列表
    - 配额：默认每日 10000 单位，search.list 单次消耗 100 单位
    - 文档：https://developers.google.com/youtube/v3/docs/search/list
"""

from __future__ import annotations

import logging
import os
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError, ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.youtube")


def resolve_api_key(legacy_field: str, env_var: str) -> str | None:
    """解析 YouTube API Key

    依次尝试：频道配置（sources.youtube.api_key）→ 旧版扁平字段
    （SouWenConfig.{legacy_field}）→ 环境变量。任一命中即返回。

    暴露为模块级函数主要便于测试时通过 ``monkeypatch.setattr(
    "souwen.web.youtube.resolve_api_key", ...)`` 直接替换。
    """
    cfg = get_config()
    key = cfg.resolve_api_key("youtube", legacy_field)
    if key:
        return key
    return os.environ.get(env_var) or None


class YouTubeClient(SouWenHttpClient):
    """YouTube Data API v3 视频搜索客户端

    需要 Google Cloud Console 创建的 API Key。无 Key 时初始化抛出
    ``ConfigError``，调度层应捕获并跳过本数据源。

    Example:
        async with YouTubeClient() as c:
            resp = await c.search("python tutorial", max_results=20,
                                  order="viewCount")
            for r in resp.results:
                print(r.title, r.url)
    """

    ENGINE_NAME = "youtube"
    BASE_URL = "https://www.googleapis.com"

    SNIPPET_MAX_LEN = 300

    VALID_ORDERS = frozenset({"relevance", "date", "rating", "viewCount", "title"})
    VALID_VIDEO_TYPES = frozenset({"any", "episode", "movie"})

    def __init__(self):
        api_key = resolve_api_key("youtube_api_key", "YOUTUBE_API_KEY")
        if not api_key:
            # 未配置 Key 时抛 ConfigError 以便调度层跳过
            raise ConfigError(
                "youtube_api_key",
                "YouTube",
                "https://console.cloud.google.com/apis/credentials",
            )

        super().__init__(
            base_url=self.BASE_URL,
            headers={"Accept": "application/json"},
            source_name="youtube",
        )
        self._api_key = api_key

    async def search(
        self,
        query: str,
        max_results: int = 10,
        order: str = "relevance",
        video_type: str | None = None,
    ) -> WebSearchResponse:
        """通过 YouTube Data API v3 搜索视频

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（YouTube 单页上限 50，超出自动截断）
            order: 排序方式 - relevance / date / rating / viewCount / title
            video_type: 视频类型过滤 - any / episode / movie；None 则不传

        Returns:
            WebSearchResponse 包含归一化后的搜索结果

        Raises:
            ValueError: order / video_type 不在允许集合中
            ParseError: YouTube 响应非 JSON 或结构异常
        """
        if order not in self.VALID_ORDERS:
            raise ValueError(
                f"无效的 order: {order!r}，可选值: {sorted(self.VALID_ORDERS)}"
            )
        if video_type is not None and video_type not in self.VALID_VIDEO_TYPES:
            raise ValueError(
                f"无效的 video_type: {video_type!r}，"
                f"可选值: {sorted(self.VALID_VIDEO_TYPES)}"
            )

        # YouTube Data API 单次最多返回 50 条，超出需翻页（这里只取首页）
        capped = max(1, min(max_results, 50))

        params: dict[str, Any] = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": capped,
            "order": order,
            "key": self._api_key,
        }
        if video_type is not None:
            params["videoType"] = video_type

        resp = await self.get("/youtube/v3/search", params=params)

        try:
            data = resp.json()
        except Exception as e:
            raise ParseError(f"YouTube 响应解析失败: {e}") from e

        items = data.get("items") or []

        results: list[WebSearchResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            snippet_data = item.get("snippet") or {}
            id_data = item.get("id") or {}
            video_id = id_data.get("videoId") if isinstance(id_data, dict) else None
            title = (snippet_data.get("title") or "").strip()
            if not video_id or not title:
                # 缺关键字段的不完整记录直接跳过
                continue

            description = (snippet_data.get("description") or "").strip()
            snippet = description[: self.SNIPPET_MAX_LEN]

            raw: dict[str, Any] = {
                "channelTitle": snippet_data.get("channelTitle"),
                "channelId": snippet_data.get("channelId"),
                "publishedAt": snippet_data.get("publishedAt"),
                "thumbnails": snippet_data.get("thumbnails"),
            }

            results.append(
                WebSearchResult(
                    source=SourceType.WEB_YOUTUBE,
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

            if len(results) >= max_results:
                break

        logger.info(
            "YouTube 返回 %d 条结果 (query=%s, order=%s)",
            len(results),
            query,
            order,
        )

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_YOUTUBE,
            results=results,
            total_results=len(results),
        )
