"""Bilibili 视频搜索客户端

文件用途：
    B 站（bilibili.com）公开搜索 API 客户端。通过 B 站 Web 端搜索接口
    检索视频内容，无需 API Key 或登录。返回结果统一映射为 SouWen 的
    WebSearchResult 模型，便于与其它 Web 数据源聚合。

    虽然 B 站接口返回的是 JSON（不是 HTML），但本客户端仍继承
    BaseScraper —— 目的是复用其 TLS 指纹伪装（curl_cffi impersonate）、
    浏览器级请求头、自适应限速与自动重试能力，避免被风控。

函数/类清单：
    BilibiliClient（类）
        - 功能：B 站视频搜索客户端
        - 继承：BaseScraper
        - 关键属性：ENGINE_NAME = "bilibili",
                  BASE_URL = "https://api.bilibili.com",
                  min_delay = 1.0, max_delay = 3.0, max_retries = 3
        - 主要方法：search(query, max_results, order) -> WebSearchResponse

    BilibiliClient.__init__(**kwargs)
        - 功能：初始化客户端，转发参数给 BaseScraper

    BilibiliClient.search(query, max_results=20, order="totalrank")
            -> WebSearchResponse
        - 功能：调用 /x/web-interface/search/type 检索视频结果
        - 输入：
            query 关键词；
            max_results 最多返回条数（B 站单页上限 50，超过会被截断）；
            order 排序方式：
                "totalrank" 综合排序（默认）
                "click"     播放量
                "pubdate"   最新发布
                "dm"        弹幕数
                "stow"      收藏数
        - 输出：WebSearchResponse，results 元素为 WebSearchResult
        - 异常：HTTP/JSON/解析异常被捕获并降级为返回空结果集

    BilibiliClient._clean_html(text) -> str
        - 功能：去除 B 站搜索结果 title 字段中的 HTML 高亮标签
                （如 <em class="keyword">…</em>）

模块依赖：
    - logging：日志
    - re：HTML 标签清理
    - urllib.parse.quote_plus：关键词 URL 编码
    - souwen.models：SourceType / WebSearchResult / WebSearchResponse
    - souwen.scraper.base：BaseScraper

技术要点：
    - 必须携带 Referer: https://www.bilibili.com，否则 API 返回 -412 风控
    - title 字段含 <em class="keyword"> 高亮标签，需要清理
    - description / snippet 截断到 300 字符以控制载荷大小
    - source 字段使用 SourceType.WEB_BILIBILI 枚举值
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus

from souwen.models import SourceType, WebSearchResponse, WebSearchResult
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.bilibili")


class BilibiliClient(BaseScraper):
    """Bilibili 视频搜索客户端

    通过 B 站公开 Web 搜索 API 检索视频，无需 API Key。

    继承 BaseScraper 是为了复用 TLS 指纹模拟、浏览器请求头、
    自适应礼貌延迟与自动重试，降低被风控的概率。

    Attributes:
        ENGINE_NAME: 引擎标识 "bilibili"
        BASE_URL:    API 基础地址 https://api.bilibili.com
    """

    ENGINE_NAME = "bilibili"
    BASE_URL = "https://api.bilibili.com"

    # B 站单页结果上限
    _MAX_PAGE_SIZE = 50
    # snippet 截断长度，避免载荷过大
    _SNIPPET_MAX_LEN = 300

    def __init__(self, **kwargs: Any) -> None:
        # 礼貌延迟 1~3 秒、最多重试 3 次；其余参数透传到 BaseScraper
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    @staticmethod
    def _clean_html(text: str) -> str:
        """清理 HTML 标签

        B 站搜索结果 title 字段中关键词会被 <em class="keyword">…</em>
        包裹用于前端高亮，本方法将所有 HTML 标签去除并 strip 空白。

        Args:
            text: 含 HTML 标签的原始文本

        Returns:
            去除标签后的纯文本；输入为空/None 时返回空串
        """
        if not text:
            return ""
        return re.sub(r"<[^>]+>", "", text).strip()

    async def search(
        self,
        query: str,
        max_results: int = 20,
        order: str = "totalrank",
    ) -> WebSearchResponse:
        """搜索 B 站视频

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（上限 50，超过被截断）
            order: 排序方式，可选
                "totalrank" 综合（默认）/ "click" 播放量 /
                "pubdate" 最新 / "dm" 弹幕数 / "stow" 收藏数

        Returns:
            WebSearchResponse，results 为 WebSearchResult 列表
        """
        page_size = max(1, min(int(max_results), self._MAX_PAGE_SIZE))
        url = (
            f"{self._resolved_base_url}/x/web-interface/search/type"
            f"?search_type=video&keyword={quote_plus(query)}"
            f"&page=1&page_size={page_size}&order={order}"
        )

        # B 站对 Referer 强校验，缺失则返回 -412 风控
        headers = {
            "Referer": "https://www.bilibili.com",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        }

        results: list[WebSearchResult] = []

        try:
            resp = await self._fetch(url, headers=headers)
        except Exception as e:  # 网络异常 → 降级为空结果，不打断聚合
            logger.warning("Bilibili 请求失败 (query=%s): %s", query, e)
            return WebSearchResponse(
                query=query,
                source=SourceType.WEB_BILIBILI,
                results=results,
                total_results=0,
            )

        try:
            payload = resp.json()
        except Exception as e:
            logger.warning("Bilibili JSON 解析失败 (query=%s): %s", query, e)
            return WebSearchResponse(
                query=query,
                source=SourceType.WEB_BILIBILI,
                results=results,
                total_results=0,
            )

        code = payload.get("code")
        if code != 0:
            # 常见：-412 风控、-101 未登录、-110 未授权
            logger.warning(
                "Bilibili API 返回错误 code=%s message=%s (query=%s)",
                code,
                payload.get("message"),
                query,
            )
            return WebSearchResponse(
                query=query,
                source=SourceType.WEB_BILIBILI,
                results=results,
                total_results=0,
            )

        data = payload.get("data") or {}
        items = data.get("result") or []
        if not isinstance(items, list):
            # /search/all/v2 端点的 data.result 是分组数组，这里兜底
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                title = self._clean_html(item.get("title", ""))
                arcurl = item.get("arcurl") or ""
                if not title or not arcurl:
                    continue

                description = (item.get("description") or "")[: self._SNIPPET_MAX_LEN]

                results.append(
                    WebSearchResult(
                        source=SourceType.WEB_BILIBILI,
                        title=title,
                        url=str(arcurl),
                        snippet=description,
                        engine=self.ENGINE_NAME,
                        raw={
                            "author": item.get("author"),
                            "mid": item.get("mid"),
                            "play": item.get("play"),
                            "video_review": item.get("video_review"),
                            "favorites": item.get("favorites"),
                            "duration": item.get("duration"),
                            "pubdate": item.get("pubdate"),
                            "tag": item.get("tag"),
                            "bvid": item.get("bvid"),
                            "aid": item.get("aid"),
                        },
                    )
                )

                if len(results) >= max_results:
                    break
            except Exception as e:
                logger.debug("Bilibili 单条结果解析失败: %s", e)
                continue

        total = data.get("numResults")
        try:
            total_int = int(total) if total is not None else len(results)
        except (TypeError, ValueError):
            total_int = len(results)

        logger.info("Bilibili 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_BILIBILI,
            results=results,
            total_results=total_int,
        )
