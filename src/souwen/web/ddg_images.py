"""DuckDuckGo 图片搜索

通过 duckduckgo.com/i.js JSON 端点获取图片搜索结果。
支持尺寸、颜色、类型、布局、许可证过滤。
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from souwen.web.ddg_json import DDGJsonClient
from souwen.web.ddg_utils import build_filter_string, normalize_url

logger = logging.getLogger("souwen.web.ddg_images")

# safesearch 映射
_SAFESEARCH_MAP = {"on": "1", "moderate": "1", "off": "-1"}


class ImageSearchResult(BaseModel):
    """图片搜索结果"""

    source: str = "duckduckgo_images"
    title: str
    url: str  # 来源页面 URL
    image_url: str  # 原图直链
    thumbnail_url: str = ""
    width: int = 0
    height: int = 0
    image_source: str = ""  # 来源站点名
    engine: str = "duckduckgo_images"


class ImageSearchResponse(BaseModel):
    """图片搜索响应"""

    query: str
    source: str = "duckduckgo_images"
    results: list[ImageSearchResult] = []
    total_results: int = 0


class DuckDuckGoImagesClient(DDGJsonClient):
    """DuckDuckGo 图片搜索客户端

    使用 i.js JSON 端点。支持尺寸/颜色/类型/布局/许可证过滤。
    """

    ENGINE_NAME = "duckduckgo_images"
    _ENDPOINT = "/i.js"
    _MAX_PAGES = 5

    async def search(
        self,
        query: str,
        max_results: int = 20,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        time_range: str | None = None,
        size: str | None = None,
        color: str | None = None,
        type_image: str | None = None,
        layout: str | None = None,
        license_image: str | None = None,
        max_pages: int | None = None,
    ) -> ImageSearchResponse:
        """搜索 DuckDuckGo 图片

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            region: 区域代码
            safesearch: "on"/"moderate"/"off"
            time_range: "Day"/"Week"/"Month"/"Year"/None
            size: "Small"/"Medium"/"Large"/"Wallpaper"/None
            color: "color"/"Monochrome"/"Red"/etc./None
            type_image: "photo"/"clipart"/"gif"/"transparent"/"line"/None
            layout: "Square"/"Tall"/"Wide"/None
            license_image: "any"/"Public"/"Share"/"ShareCommercially"/"Modify"/"ModifyCommercially"/None
            max_pages: 最大分页数

        Returns:
            ImageSearchResponse 包含图片搜索结果
        """
        vqd = await self._get_vqd(query)
        if not vqd:
            return ImageSearchResponse(query=query)

        # 构建过滤字符串
        time_token = f"time:{time_range}" if time_range else ""
        size_token = f"size:{size}" if size else ""
        color_token = f"color:{color}" if color else ""
        type_token = f"type:{type_image}" if type_image else ""
        layout_token = f"layout:{layout}" if layout else ""
        license_token = f"license:{license_image}" if license_image else ""
        f_str = build_filter_string(
            time_token, size_token, color_token, type_token, layout_token, license_token
        )

        params: dict[str, str] = {
            "l": region,
            "o": "json",
            "q": query,
            "vqd": vqd,
            "f": f_str,
            "p": _SAFESEARCH_MAP.get(safesearch, "1"),
        }

        raw_results = await self._paginated_search(query, params, max_results, max_pages)

        results: list[ImageSearchResult] = []
        seen_images: set[str] = set()

        for row in raw_results:
            image_url = normalize_url(row.get("image", ""))
            if not image_url or image_url in seen_images:
                continue
            seen_images.add(image_url)

            results.append(
                ImageSearchResult(
                    title=row.get("title", ""),
                    url=normalize_url(row.get("url", "")),
                    image_url=image_url,
                    thumbnail_url=normalize_url(row.get("thumbnail", "")),
                    width=int(row.get("width", 0) or 0),
                    height=int(row.get("height", 0) or 0),
                    image_source=row.get("source", ""),
                )
            )

        logger.info("DDG Images 返回 %d 条结果 (query=%s)", len(results), query)
        return ImageSearchResponse(
            query=query,
            results=results,
            total_results=len(results),
        )
