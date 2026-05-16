"""YouTube Data API v3 全功能客户端

文件用途：
    YouTube Data API v3 客户端，提供视频搜索（含分页）、热门视频、
    视频详情、字幕提取等功能。需要 API Key（通过配置字段 youtube_api_key
    或环境变量 YOUTUBE_API_KEY 提供），无 Key 时客户端初始化会抛出
    ConfigError 以便调度层（integration_type=official_api）跳过该数据源。

类清单：
    VideoDetail — 视频详情数据类（含统计和时长）
    YouTubeClient — 完整 YouTube API 客户端

方法清单：
    search() — 视频搜索（支持分页、日期/地区/语言/频道过滤、统计信息增强）
    get_trending() — 热门视频（按地区/分类）
    get_video_details() — 批量获取视频详情
    get_transcript() — 提取视频字幕文本

配额说明：
    - 默认每日 10,000 单位
    - search.list: 100 单位/次
    - videos.list: 1 单位/次
    - 多页搜索消耗 = 页数 × 100
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, ParseError, RateLimitError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.youtube")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_PER_PAGE = 50
_ABSOLUTE_MAX_RESULTS = 200  # 安全上限，避免配额爆表（4 页 = 400 单位）
_VIDEOS_BATCH_SIZE = 50  # videos.list 单次最多 50 个 ID

# YouTube 视频分类 ID 参考
CATEGORY_IDS = {
    "film": "1",
    "autos": "2",
    "music": "10",
    "pets": "15",
    "sports": "17",
    "gaming": "20",
    "people": "22",
    "comedy": "23",
    "entertainment": "24",
    "news": "25",
    "howto": "26",
    "education": "27",
    "science": "28",
}


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class VideoDetail:
    """视频详情数据"""

    video_id: str
    title: str
    description: str = ""
    channel_title: str = ""
    channel_id: str = ""
    published_at: str = ""
    thumbnail_url: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration_seconds: int = 0
    tags: list[str] = field(default_factory=list)
    category_id: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _parse_iso8601_duration(duration: str) -> int:
    """解析 ISO 8601 时长为秒数（如 PT4M13S → 253）"""
    m = re.match(
        r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$",
        duration or "",
    )
    if not m:
        return 0
    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    seconds = int(m.group(4) or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class YouTubeClient(SouWenHttpClient):
    """YouTube Data API v3 全功能客户端

    功能：视频搜索（分页、过滤、增强）、热门视频、视频详情、字幕提取。
    需要 Google Cloud Console 创建的 API Key。

    Example:
        async with YouTubeClient() as c:
            # 基础搜索
            resp = await c.search("python tutorial", max_results=20)

            # 高级搜索：带过滤和统计增强
            resp = await c.search(
                "machine learning",
                max_results=100,
                order="viewCount",
                published_after="2024-01-01T00:00:00Z",
                region_code="US",
                enrich=True,
            )

            # 热门视频
            trending = await c.get_trending(region_code="JP", category_id="20")

            # 视频详情
            details = await c.get_video_details(["dQw4w9WgXcQ", "jNQXAC9IVRw"])

            # 字幕提取
            transcript = await c.get_transcript("dQw4w9WgXcQ", lang="en")
    """

    ENGINE_NAME = "youtube"
    BASE_URL = "https://www.googleapis.com"

    SNIPPET_MAX_LEN = 300

    VALID_ORDERS = frozenset({"relevance", "date", "rating", "viewCount", "title"})
    VALID_VIDEO_TYPES = frozenset({"any", "episode", "movie"})

    def __init__(self):
        api_key = resolve_api_key("youtube_api_key", "YOUTUBE_API_KEY")
        if not api_key:
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

    # ------------------------------------------------------------------
    # Override: YouTube 特殊的 403 处理（配额超限 vs 权限不足）
    # ------------------------------------------------------------------

    @staticmethod
    def _check_response(resp: Any, url: str) -> None:
        """YouTube 专用响应检查：区分配额超限和普通 403"""
        if resp.status_code == 403:
            try:
                data = resp.json()
                errors = data.get("error", {}).get("errors", [])
                if any(e.get("reason") == "quotaExceeded" for e in errors):
                    raise RateLimitError(
                        "YouTube API 每日配额已用尽，请明日再试",
                        retry_after=86400.0,
                    )
                if any(e.get("reason") == "rateLimitExceeded" for e in errors):
                    raise RateLimitError(
                        "YouTube API 请求频率过高",
                        retry_after=60.0,
                    )
            except (ValueError, AttributeError, KeyError):
                pass
        # 其余状态码由父类统一处理
        SouWenHttpClient._check_response(resp, url)

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 10,
        order: str = "relevance",
        video_type: str | None = None,
        *,
        published_after: str | None = None,
        published_before: str | None = None,
        region_code: str | None = None,
        relevance_language: str | None = None,
        video_category_id: str | None = None,
        channel_id: str | None = None,
        enrich: bool = False,
    ) -> WebSearchResponse:
        """搜索 YouTube 视频

        支持多页分页（max_results > 50 时自动翻页），以及丰富的过滤条件。
        可选通过 videos.list 增强统计信息（播放量/点赞/评论/时长）。

        Args:
            query: 搜索关键词
            max_results: 最大返回数（上限 200，超出截断）
            order: 排序 - relevance/date/rating/viewCount/title
            video_type: 类型过滤 - any/episode/movie
            published_after: 发布时间下限（RFC 3339，如 2024-01-01T00:00:00Z）
            published_before: 发布时间上限
            region_code: 地区码（ISO 3166-1 alpha-2，如 US/CN/JP）
            relevance_language: 相关语言（ISO 639-1，如 en/zh/ja）
            video_category_id: 视频分类 ID（参见 CATEGORY_IDS）
            channel_id: 限定频道
            enrich: 是否增强统计信息（额外 1 单位/50 视频配额）

        Returns:
            WebSearchResponse

        Raises:
            ValueError: 参数不合法
            ParseError: 响应解析失败
            RateLimitError: 配额超限
        """
        if order not in self.VALID_ORDERS:
            raise ValueError(f"无效的 order: {order!r}，可选值: {sorted(self.VALID_ORDERS)}")
        if video_type is not None and video_type not in self.VALID_VIDEO_TYPES:
            raise ValueError(
                f"无效的 video_type: {video_type!r}，可选值: {sorted(self.VALID_VIDEO_TYPES)}"
            )

        # 安全上限
        target = max(1, min(max_results, _ABSOLUTE_MAX_RESULTS))
        if max_results > _ABSOLUTE_MAX_RESULTS:
            logger.warning(
                "max_results=%d 超出安全上限 %d，已截断",
                max_results,
                _ABSOLUTE_MAX_RESULTS,
            )

        # 构建基础参数
        base_params: dict[str, Any] = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": order,
            "key": self._api_key,
        }
        if video_type is not None:
            base_params["videoType"] = video_type
        if published_after:
            base_params["publishedAfter"] = published_after
        if published_before:
            base_params["publishedBefore"] = published_before
        if region_code:
            base_params["regionCode"] = region_code
        if relevance_language:
            base_params["relevanceLanguage"] = relevance_language
        if video_category_id:
            base_params["videoCategoryId"] = video_category_id
        if channel_id:
            base_params["channelId"] = channel_id

        # 分页循环
        all_items: list[dict] = []
        page_token: str | None = None
        pages_fetched = 0

        while len(all_items) < target:
            per_page = min(_MAX_PER_PAGE, target - len(all_items))
            params = {**base_params, "maxResults": per_page}
            if page_token:
                params["pageToken"] = page_token

            resp = await self.get("/youtube/v3/search", params=params)
            data = self._parse_json(resp)

            items = data.get("items") or []
            all_items.extend(items)
            pages_fetched += 1

            page_token = data.get("nextPageToken")
            if not page_token or not items:
                break

            if pages_fetched > 1:
                logger.info(
                    "YouTube 搜索翻页中: 已获取 %d 条，第 %d 页",
                    len(all_items),
                    pages_fetched,
                )

        # 解析结果
        results = self._parse_search_items(all_items[:target])

        # 可选: 统计信息增强
        if enrich and results:
            results = await self._enrich_results(results)

        logger.info(
            "YouTube 搜索完成: %d 条结果, %d 页 (query=%s, order=%s)",
            len(results),
            pages_fetched,
            query,
            order,
        )

        return WebSearchResponse(
            query=query,
            source="youtube",
            results=results,
            total_results=len(results),
        )

    # ------------------------------------------------------------------
    # 热门视频
    # ------------------------------------------------------------------

    async def get_trending(
        self,
        region_code: str = "US",
        category_id: str | None = None,
        max_results: int = 10,
    ) -> WebSearchResponse:
        """获取热门/流行视频

        Args:
            region_code: 地区码（ISO 3166-1 alpha-2）
            category_id: 视频分类 ID（参见 CATEGORY_IDS）
            max_results: 最大返回数（上限 50）

        Returns:
            WebSearchResponse（query 格式为 "trending:{region}:{category}"）
        """
        capped = max(1, min(max_results, _MAX_PER_PAGE))

        params: dict[str, Any] = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": capped,
            "key": self._api_key,
        }
        if category_id:
            params["videoCategoryId"] = category_id

        resp = await self.get("/youtube/v3/videos", params=params)
        data = self._parse_json(resp)

        items = data.get("items") or []
        results: list[WebSearchResult] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            video_id = item.get("id", "")
            snippet_data = item.get("snippet") or {}
            stats = item.get("statistics") or {}
            title = (snippet_data.get("title") or "").strip()
            if not video_id or not title:
                continue

            description = (snippet_data.get("description") or "").strip()

            raw: dict[str, Any] = {
                "channelTitle": snippet_data.get("channelTitle"),
                "channelId": snippet_data.get("channelId"),
                "publishedAt": snippet_data.get("publishedAt"),
                "thumbnails": snippet_data.get("thumbnails"),
                "viewCount": int(stats.get("viewCount", 0)),
                "likeCount": int(stats.get("likeCount", 0)),
                "commentCount": int(stats.get("commentCount", 0)),
            }

            results.append(
                WebSearchResult(
                    source="youtube",
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    snippet=description[: self.SNIPPET_MAX_LEN],
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        query_label = f"trending:{region_code}"
        if category_id:
            query_label += f":{category_id}"

        return WebSearchResponse(
            query=query_label,
            source="youtube",
            results=results,
            total_results=len(results),
        )

    # ------------------------------------------------------------------
    # 视频详情
    # ------------------------------------------------------------------

    async def get_video_details(self, video_ids: list[str]) -> list[VideoDetail]:
        """批量获取视频详情（含统计信息和时长）

        Args:
            video_ids: 视频 ID 列表（自动去重，保留顺序）

        Returns:
            VideoDetail 列表（不存在/私有的视频会被跳过）
        """
        # 去重并保留顺序
        seen: set[str] = set()
        unique_ids: list[str] = []
        for vid in video_ids:
            if vid not in seen:
                seen.add(vid)
                unique_ids.append(vid)

        all_details: dict[str, VideoDetail] = {}

        # 分批请求（每批最多 50）
        for i in range(0, len(unique_ids), _VIDEOS_BATCH_SIZE):
            batch = unique_ids[i : i + _VIDEOS_BATCH_SIZE]
            params: dict[str, Any] = {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "key": self._api_key,
            }

            resp = await self.get("/youtube/v3/videos", params=params)
            data = self._parse_json(resp)

            for item in data.get("items") or []:
                detail = self._parse_video_item(item)
                if detail:
                    all_details[detail.video_id] = detail

        # 保留输入顺序
        return [all_details[vid] for vid in unique_ids if vid in all_details]

    # ------------------------------------------------------------------
    # 字幕提取
    # ------------------------------------------------------------------

    async def get_transcript(
        self,
        video_id: str,
        lang: str = "en",
    ) -> str | None:
        """提取视频字幕文本

        通过解析视频页面获取字幕轨道信息，然后下载字幕 XML 并提取纯文本。
        此功能不消耗 YouTube Data API 配额。

        Args:
            video_id: 视频 ID
            lang: 首选语言代码（如 en/zh/ja），找不到时尝试第一个可用轨道

        Returns:
            字幕全文（各段落以换行分隔），无字幕时返回 None
        """
        try:
            # 获取视频页面，提取字幕轨道
            caption_url = await self._get_caption_url(video_id, lang)
            if not caption_url:
                return None

            # 下载字幕 XML
            resp = await self._client.request("GET", caption_url)
            if resp.status_code != 200:
                logger.debug("字幕下载失败: %d for video %s", resp.status_code, video_id)
                return None

            # 解析 XML 提取文本
            return self._parse_caption_xml(resp.text)

        except Exception as e:
            logger.debug("字幕提取失败 (video=%s): %s", video_id, e)
            return None

    # ------------------------------------------------------------------
    # Private Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(resp: Any) -> dict:
        """解析 JSON 响应"""
        try:
            return resp.json()
        except Exception as e:
            raise ParseError(f"YouTube 响应解析失败: {e}") from e

    def _parse_search_items(self, items: list[dict]) -> list[WebSearchResult]:
        """将 search.list items 转为 WebSearchResult"""
        results: list[WebSearchResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            snippet_data = item.get("snippet") or {}
            id_data = item.get("id") or {}
            video_id = id_data.get("videoId") if isinstance(id_data, dict) else None
            title = (snippet_data.get("title") or "").strip()
            if not video_id or not title:
                continue

            description = (snippet_data.get("description") or "").strip()

            raw: dict[str, Any] = {
                "channelTitle": snippet_data.get("channelTitle"),
                "channelId": snippet_data.get("channelId"),
                "publishedAt": snippet_data.get("publishedAt"),
                "thumbnails": snippet_data.get("thumbnails"),
            }

            results.append(
                WebSearchResult(
                    source="youtube",
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    snippet=description[: self.SNIPPET_MAX_LEN],
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )
        return results

    async def _enrich_results(self, results: list[WebSearchResult]) -> list[WebSearchResult]:
        """通过 videos.list 增强搜索结果的统计信息"""
        # 提取 video IDs
        video_ids: list[str] = []
        for r in results:
            vid = r.url.rsplit("v=", 1)[-1] if "v=" in r.url else ""
            if vid:
                video_ids.append(vid)

        if not video_ids:
            return results

        # 批量获取统计
        stats_map: dict[str, dict] = {}
        try:
            for i in range(0, len(video_ids), _VIDEOS_BATCH_SIZE):
                batch = video_ids[i : i + _VIDEOS_BATCH_SIZE]
                params: dict[str, Any] = {
                    "part": "statistics,contentDetails",
                    "id": ",".join(batch),
                    "key": self._api_key,
                }
                resp = await self.get("/youtube/v3/videos", params=params)
                data = self._parse_json(resp)
                for item in data.get("items") or []:
                    vid = item.get("id", "")
                    stats = item.get("statistics") or {}
                    content = item.get("contentDetails") or {}
                    stats_map[vid] = {
                        "viewCount": int(stats.get("viewCount", 0)),
                        "likeCount": int(stats.get("likeCount", 0)),
                        "commentCount": int(stats.get("commentCount", 0)),
                        "duration": content.get("duration", ""),
                        "durationSeconds": _parse_iso8601_duration(content.get("duration", "")),
                    }
        except Exception as e:
            # 增强失败不影响主搜索结果
            logger.warning("统计增强失败，返回原始结果: %s", e)
            return results

        # 将统计信息合并到 raw
        enriched: list[WebSearchResult] = []
        for r, vid in zip(results, video_ids):
            if vid in stats_map:
                new_raw = {**(r.raw or {}), **stats_map[vid]}
                enriched.append(
                    WebSearchResult(
                        source=r.source,
                        title=r.title,
                        url=r.url,
                        snippet=r.snippet,
                        engine=r.engine,
                        raw=new_raw,
                    )
                )
            else:
                enriched.append(r)
        return enriched

    @staticmethod
    def _parse_video_item(item: dict) -> VideoDetail | None:
        """解析 videos.list 单条 item 为 VideoDetail"""
        video_id = item.get("id", "")
        snippet = item.get("snippet") or {}
        stats = item.get("statistics") or {}
        content = item.get("contentDetails") or {}

        title = (snippet.get("title") or "").strip()
        if not video_id or not title:
            return None

        thumbnails = snippet.get("thumbnails") or {}
        thumb = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url", "")
        )

        return VideoDetail(
            video_id=video_id,
            title=title,
            description=(snippet.get("description") or "").strip(),
            channel_title=snippet.get("channelTitle", ""),
            channel_id=snippet.get("channelId", ""),
            published_at=snippet.get("publishedAt", ""),
            thumbnail_url=thumb,
            view_count=int(stats.get("viewCount", 0)),
            like_count=int(stats.get("likeCount", 0)),
            comment_count=int(stats.get("commentCount", 0)),
            duration_seconds=_parse_iso8601_duration(content.get("duration", "")),
            tags=snippet.get("tags") or [],
            category_id=snippet.get("categoryId", ""),
        )

    async def _get_caption_url(self, video_id: str, lang: str) -> str | None:
        """从视频页面提取字幕轨道 URL"""
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            resp = await self._client.request(
                "GET",
                watch_url,
                headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
            )
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        html = resp.text

        # 提取 captionTracks 从 ytInitialPlayerResponse
        match = re.search(
            r'"captionTracks"\s*:\s*(\[.*?\])',
            html,
        )
        if not match:
            return None

        try:
            tracks = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            return None

        if not tracks:
            return None

        # 查找匹配语言的轨道
        target_track = None
        for track in tracks:
            code = track.get("languageCode", "")
            if code == lang or code.startswith(f"{lang}-"):
                target_track = track
                break

        # 回退到第一个轨道
        if not target_track:
            target_track = tracks[0]

        base_url = target_track.get("baseUrl", "")
        if not base_url:
            return None

        return base_url

    @staticmethod
    def _parse_caption_xml(xml_text: str) -> str | None:
        """解析字幕 XML，提取纯文本"""
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return None

        segments: list[str] = []
        for elem in root.iter("text"):
            text = elem.text
            if text:
                # 替换 HTML 实体和换行
                text = text.replace("&amp;", "&")
                text = text.replace("&lt;", "<")
                text = text.replace("&gt;", ">")
                text = text.replace("&#39;", "'")
                text = text.replace("&quot;", '"')
                text = text.replace("\n", " ")
                segments.append(text.strip())

        if not segments:
            return None

        return "\n".join(segments)
