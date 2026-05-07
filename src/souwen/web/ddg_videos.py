"""DuckDuckGo 视频搜索

通过 duckduckgo.com/v.js JSON 端点获取视频搜索结果。
支持分辨率、时长、许可证过滤。
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from souwen.web.ddg_json import DDGJsonClient
from souwen.web.ddg_utils import build_filter_string

logger = logging.getLogger("souwen.web.ddg_videos")

_SAFESEARCH_MAP = {"on": "1", "moderate": "-1", "off": "-2"}


class VideoSearchResult(BaseModel):
    """视频搜索结果"""

    source: str = "duckduckgo_videos"
    title: str
    url: str  # 视频页面 URL
    duration: str = ""
    publisher: str = ""
    published: str = ""
    description: str = ""
    thumbnail: str = ""
    embed_url: str = ""
    view_count: int = 0
    engine: str = "duckduckgo_videos"


class VideoSearchResponse(BaseModel):
    """视频搜索响应"""

    query: str
    source: str = "duckduckgo_videos"
    results: list[VideoSearchResult] = []
    total_results: int = 0


class DuckDuckGoVideosClient(DDGJsonClient):
    """DuckDuckGo 视频搜索客户端

    使用 v.js JSON 端点。支持分辨率/时长/许可证过滤。
    """

    ENGINE_NAME = "duckduckgo_videos"
    _ENDPOINT = "/v.js"
    _MAX_PAGES = 8

    async def search(
        self,
        query: str,
        max_results: int = 20,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        time_range: str | None = None,
        resolution: str | None = None,
        duration: str | None = None,
        license_videos: str | None = None,
        max_pages: int | None = None,
    ) -> VideoSearchResponse:
        """搜索 DuckDuckGo 视频

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            region: 区域代码
            safesearch: "on"/"moderate"/"off"
            time_range: "d"(天)/"w"(周)/"m"(月)/None
            resolution: "high"/"standard"/None
            duration: "short"/"medium"/"long"/None
            license_videos: "creativeCommon"/"youtube"/None
            max_pages: 最大分页数

        Returns:
            VideoSearchResponse 包含视频搜索结果
        """
        vqd = await self._get_vqd(query)
        if not vqd:
            return VideoSearchResponse(query=query)

        # 构建过滤字符串
        time_token = f"publishedAfter:{time_range}" if time_range else ""
        res_token = f"videoDefinition:{resolution}" if resolution else ""
        dur_token = f"videoDuration:{duration}" if duration else ""
        lic_token = f"videoLicense:{license_videos}" if license_videos else ""
        f_str = build_filter_string(time_token, res_token, dur_token, lic_token)

        params: dict[str, str] = {
            "l": region,
            "o": "json",
            "q": query,
            "vqd": vqd,
            "f": f_str,
            "p": _SAFESEARCH_MAP.get(safesearch, "-1"),
        }

        raw_results = await self._paginated_search(query, params, max_results, max_pages)

        results: list[VideoSearchResult] = []
        seen_urls: set[str] = set()

        for row in raw_results:
            url = row.get("content", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # 提取观看次数
            view_count = 0
            stats = row.get("statistics", {})
            if isinstance(stats, dict):
                view_count = int(stats.get("viewCount", 0) or 0)

            # 提取缩略图
            thumbnail = ""
            images = row.get("images", {})
            if isinstance(images, dict):
                thumbnail = (
                    images.get("large", "") or images.get("medium", "") or images.get("small", "")
                )

            results.append(
                VideoSearchResult(
                    title=row.get("title", ""),
                    url=url,
                    duration=row.get("duration", ""),
                    publisher=row.get("publisher", ""),
                    published=row.get("published", ""),
                    description=row.get("description", ""),
                    thumbnail=thumbnail,
                    embed_url=row.get("embed_url", ""),
                    view_count=view_count,
                )
            )

        logger.info("DDG Videos 返回 %d 条结果 (query=%s)", len(results), query)
        return VideoSearchResponse(
            query=query,
            results=results,
            total_results=len(results),
        )
