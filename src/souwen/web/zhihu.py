"""知乎搜索客户端

文件用途：
    知乎（zhihu.com）搜索客户端。通过知乎 Web 端搜索 API
    检索问题和回答内容，无需 API Key 或登录。返回结果统一映射为
    SouWen 的 WebSearchResult 模型，便于与其它数据源聚合。

    本客户端继承 BaseScraper —— 目的是复用其 TLS 指纹伪装
    （curl_cffi impersonate）、浏览器级请求头、自适应限速与
    自动重试能力，避免被风控。

函数/类清单：
    ZhihuClient（类）
        - 功能：知乎搜索客户端
        - 继承：BaseScraper
        - 关键属性：ENGINE_NAME = "zhihu",
                  BASE_URL = "https://www.zhihu.com",
                  min_delay = 1.5, max_delay = 4.0, max_retries = 3
        - 主要方法：search(query, max_results, search_type)
                    -> WebSearchResponse

    ZhihuClient.__init__(**kwargs)
        - 功能：初始化客户端，转发参数给 BaseScraper

    ZhihuClient.search(query, max_results=10, search_type="general")
            -> WebSearchResponse
        - 功能：调用 /api/v4/search_v3 检索问答/文章结果
        - 输入：
            query        关键词；
            max_results  最多返回条数（知乎单页上限 20，超过被截断）；
            search_type  搜索类型（默认 "general"，即综合）
        - 输出：WebSearchResponse，results 元素为 WebSearchResult
        - 异常：HTTP/JSON/解析异常被捕获并降级为返回空结果集

    ZhihuClient._clean_html(text) -> str
        - 功能：去除知乎搜索摘要中的 HTML 高亮标签
                （如 <em>关键词</em>）

模块依赖：
    - logging：日志
    - re：HTML 标签清理
    - urllib.parse.quote_plus：关键词 URL 编码
    - souwen.models：WebSearchResult / WebSearchResponse
    - souwen.core.scraper.base：BaseScraper

技术要点：
    - 必须携带 Referer: https://www.zhihu.com/search 与
      x-requested-with: fetch，否则 API 易被 403 拦截
    - 结果按 object.type 分别处理：answer / question / article
    - excerpt 字段含 <em> 高亮标签，需要清理
    - snippet 截断到 300 字符以控制载荷大小
    - source 字段使用 'zhihu' 枚举值
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus

from souwen.models import WebSearchResponse, WebSearchResult
from souwen.core.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.zhihu")


class ZhihuClient(BaseScraper):
    """知乎搜索客户端

    通过知乎公开 Web 搜索 API 检索问答与文章，无需 API Key。

    继承 BaseScraper 是为了复用 TLS 指纹模拟、浏览器请求头、
    自适应礼貌延迟与自动重试，降低被风控的概率。

    Attributes:
        ENGINE_NAME: 引擎标识 "zhihu"
        BASE_URL:    基础地址 https://www.zhihu.com
    """

    ENGINE_NAME = "zhihu"
    BASE_URL = "https://www.zhihu.com"

    # 知乎单页结果上限
    _MAX_PAGE_SIZE = 20
    # snippet 截断长度，避免载荷过大
    _SNIPPET_MAX_LEN = 300

    def __init__(self, **kwargs: Any) -> None:
        # 礼貌延迟 1.5~4 秒、最多重试 3 次；其余参数透传到 BaseScraper
        super().__init__(min_delay=1.5, max_delay=4.0, max_retries=3, **kwargs)

    @staticmethod
    def _clean_html(text: str) -> str:
        """清理 HTML 标签

        知乎搜索摘要中关键词会被 <em>…</em> 包裹用于前端高亮，
        本方法将所有 HTML 标签去除并 strip 空白。

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
        max_results: int = 10,
        search_type: str = "general",
    ) -> WebSearchResponse:
        """搜索知乎内容

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（上限 20，超过被截断）
            search_type: 搜索类型，默认 "general"（综合）

        Returns:
            WebSearchResponse，results 为 WebSearchResult 列表
        """
        page_size = max(1, min(int(max_results), self._MAX_PAGE_SIZE))
        url = (
            f"{self._resolved_base_url}/api/v4/search_v3"
            f"?t={search_type}&q={quote_plus(query)}"
            f"&correction=1&offset=0&limit={page_size}"
        )

        # 知乎对请求头较敏感，缺失 Referer / x-requested-with 容易 403
        headers = {
            "Referer": "https://www.zhihu.com/search",
            "Accept": "application/json, text/plain, */*",
            "x-requested-with": "fetch",
        }

        results: list[WebSearchResult] = []

        try:
            resp = await self._fetch(url, headers=headers)
        except Exception as e:  # 网络异常 → 降级为空结果，不打断聚合
            logger.warning("Zhihu 请求失败 (query=%s): %s", query, e)
            return WebSearchResponse(
                query=query,
                source="zhihu",
                results=results,
                total_results=0,
            )

        try:
            payload = resp.json()
        except Exception as e:
            logger.warning("Zhihu JSON 解析失败 (query=%s): %s", query, e)
            return WebSearchResponse(
                query=query,
                source="zhihu",
                results=results,
                total_results=0,
            )

        items = payload.get("data") or []
        if not isinstance(items, list):
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                obj = item.get("object")
                if not isinstance(obj, dict):
                    continue

                obj_type = obj.get("type") or ""
                title = ""
                url_value = ""

                if obj_type == "answer":
                    question = obj.get("question") or {}
                    if isinstance(question, dict):
                        title = self._clean_html(question.get("title", ""))
                    url_value = obj.get("url") or ""
                elif obj_type == "question":
                    title = self._clean_html(obj.get("title", ""))
                    url_value = obj.get("url") or (
                        f"https://www.zhihu.com/question/{obj.get('id')}"
                        if obj.get("id") is not None
                        else ""
                    )
                elif obj_type == "article":
                    title = self._clean_html(obj.get("title", ""))
                    url_value = obj.get("url") or ""
                else:
                    # 未知类型尽力而为
                    title = self._clean_html(
                        obj.get("title", "") or (obj.get("question") or {}).get("title", "")
                        if isinstance(obj.get("question"), dict)
                        else obj.get("title", "")
                    )
                    url_value = obj.get("url") or ""

                if not title or not url_value:
                    continue

                snippet = self._clean_html(obj.get("excerpt", ""))[: self._SNIPPET_MAX_LEN]

                author_info = obj.get("author") or {}
                author_name = author_info.get("name") if isinstance(author_info, dict) else None

                results.append(
                    WebSearchResult(
                        source="zhihu",
                        title=title,
                        url=str(url_value),
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                        raw={
                            "type": obj_type,
                            "id": obj.get("id"),
                            "author": author_name,
                            "voteup_count": obj.get("voteup_count"),
                        },
                    )
                )

                if len(results) >= max_results:
                    break
            except Exception as e:
                logger.debug("Zhihu 单条结果解析失败: %s", e)
                continue

        paging = payload.get("paging") or {}
        total = paging.get("totals") if isinstance(paging, dict) else None
        try:
            total_int = int(total) if total is not None else len(results)
        except (TypeError, ValueError):
            total_int = len(results)

        logger.info("Zhihu 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="zhihu",
            results=results,
            total_results=total_int,
        )
