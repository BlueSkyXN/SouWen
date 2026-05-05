"""微博搜索客户端

文件用途：
    微博（m.weibo.cn）移动端搜索 API 客户端。通过微博公开的移动端
    容器接口检索微博内容，无需 API Key 或登录。返回结果统一映射为
    SouWen 的 WebSearchResult 模型，便于与其它数据源聚合。

    本客户端继承 BaseScraper —— 目的是复用其 TLS 指纹伪装
    （curl_cffi impersonate）、浏览器级请求头、自适应限速与
    自动重试能力，避免被风控。

函数/类清单：
    WeiboClient（类）
        - 功能：微博移动端搜索客户端
        - 继承：BaseScraper
        - 关键属性：ENGINE_NAME = "weibo",
                  BASE_URL = "https://m.weibo.cn",
                  min_delay = 2.0, max_delay = 5.0, max_retries = 3
        - 主要方法：search(query, max_results) -> WebSearchResponse

    WeiboClient.__init__(**kwargs)
        - 功能：初始化客户端，转发参数给 BaseScraper

    WeiboClient.search(query, max_results=10) -> WebSearchResponse
        - 功能：调用 /api/container/getIndex 检索微博内容
        - 输入：
            query 关键词；
            max_results 最多返回条数（移动端单页约 10 条）
        - 输出：WebSearchResponse，results 元素为 WebSearchResult
        - 异常：HTTP/JSON/解析异常被捕获并降级为返回空结果集

    WeiboClient._clean_html(text) -> str
        - 功能：清理微博正文中的 HTML 标签（<p>、<br>、<a> 等），
                以及多余空白；用于生成纯文本 title / snippet

模块依赖：
    - logging：日志
    - re：HTML 标签清理
    - urllib.parse.quote_plus：关键词 URL 编码
    - souwen.models：SourceType / WebSearchResult / WebSearchResponse
    - souwen.core.scraper.base：BaseScraper

技术要点：
    - containerid 形如 100103type=1&q={query} 经 URL 编码后传入
    - 必须携带 Referer: https://m.weibo.cn/search 与
      X-Requested-With: XMLHttpRequest，否则容易被风控
    - 仅处理 card_type == 9 的卡片（普通微博），跳过话题/用户等卡片
    - 微博无独立标题，取正文清洗后前 100 字符作为 title
    - snippet 截断到 300 字符，控制载荷大小
    - source 字段使用 SourceType.WEB_WEIBO 枚举值
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus

from souwen.models import SourceType, WebSearchResponse, WebSearchResult
from souwen.core.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.weibo")


class WeiboClient(BaseScraper):
    """微博移动端搜索客户端

    通过微博公开的移动端容器接口检索微博内容，无需 API Key 或登录。

    继承 BaseScraper 是为了复用 TLS 指纹模拟、浏览器请求头、
    自适应礼貌延迟与自动重试，降低被风控的概率。

    Attributes:
        ENGINE_NAME: 引擎标识 "weibo"
        BASE_URL:    API 基础地址 https://m.weibo.cn
    """

    ENGINE_NAME = "weibo"
    BASE_URL = "https://m.weibo.cn"

    # 微博移动端单页约 10 条
    _MAX_PAGE_SIZE = 10
    # snippet 截断长度
    _SNIPPET_MAX_LEN = 300
    # title 截断长度（微博无标题，取正文前若干字符）
    _TITLE_MAX_LEN = 100

    def __init__(self, **kwargs: Any) -> None:
        # 礼貌延迟 2~5 秒、最多重试 3 次；其余参数透传到 BaseScraper
        super().__init__(min_delay=2.0, max_delay=5.0, max_retries=3, **kwargs)

    @staticmethod
    def _clean_html(text: str) -> str:
        """清理微博正文 HTML 标签

        微博正文 mblog.text 中包含 <p>、<br />、<a>、表情图标 <span>
        等 HTML 片段，本方法将所有标签去除，并把 <br> 替换为空格、
        合并多余空白。

        Args:
            text: 含 HTML 标签的原始正文

        Returns:
            去除标签后的纯文本；输入为空/None 时返回空串
        """
        if not text:
            return ""
        # 先把 <br /> 替换为空格，避免多行被粘连
        text = re.sub(r"<br\s*/?>", " ", text)
        # 移除所有剩余 HTML 标签
        text = re.sub(r"<[^>]+>", "", text)
        # 合并多余空白
        text = re.sub(r"\s+", " ", text).strip()
        return text

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> WebSearchResponse:
        """搜索微博内容

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（移动端单页约 10 条）

        Returns:
            WebSearchResponse，results 为 WebSearchResult 列表
        """
        # containerid = 100103type=1&q={query}，再做一次 URL 编码
        url = (
            f"{self._resolved_base_url}/api/container/getIndex"
            f"?containerid=100103type%3D1%26q%3D{quote_plus(query)}"
            f"&page_type=searchall"
        )

        # 微博对 Referer / X-Requested-With 强校验
        headers = {
            "Referer": "https://m.weibo.cn/search",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }

        results: list[WebSearchResult] = []

        try:
            resp = await self._fetch(url, headers=headers)
        except Exception as e:  # 网络异常 → 降级为空结果，不打断聚合
            logger.warning("微博请求失败 (query=%s): %s", query, e)
            return WebSearchResponse(
                query=query,
                source=SourceType.WEB_WEIBO,
                results=results,
                total_results=0,
            )

        try:
            payload = resp.json()
        except Exception as e:
            logger.warning("微博 JSON 解析失败 (query=%s): %s", query, e)
            return WebSearchResponse(
                query=query,
                source=SourceType.WEB_WEIBO,
                results=results,
                total_results=0,
            )

        ok = payload.get("ok")
        if ok != 1:
            logger.warning(
                "微博 API 返回非 OK ok=%s msg=%s (query=%s)",
                ok,
                payload.get("msg"),
                query,
            )
            return WebSearchResponse(
                query=query,
                source=SourceType.WEB_WEIBO,
                results=results,
                total_results=0,
            )

        data = payload.get("data") or {}
        cards = data.get("cards") or []
        if not isinstance(cards, list):
            cards = []

        for card in cards:
            if not isinstance(card, dict):
                continue
            # 仅保留普通微博卡片
            if card.get("card_type") != 9:
                continue

            mblog = card.get("mblog")
            if not isinstance(mblog, dict):
                continue

            try:
                cleaned = self._clean_html(mblog.get("text", ""))
                if not cleaned:
                    continue

                mblog_id = mblog.get("id")
                if not mblog_id:
                    continue

                title = cleaned[: self._TITLE_MAX_LEN]
                snippet = cleaned[: self._SNIPPET_MAX_LEN]
                detail_url = f"https://m.weibo.cn/detail/{mblog_id}"

                user = mblog.get("user") or {}
                screen_name = user.get("screen_name") if isinstance(user, dict) else None

                results.append(
                    WebSearchResult(
                        source=SourceType.WEB_WEIBO,
                        title=title,
                        url=detail_url,
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                        raw={
                            "user": screen_name,
                            "reposts_count": mblog.get("reposts_count"),
                            "comments_count": mblog.get("comments_count"),
                            "attitudes_count": mblog.get("attitudes_count"),
                            "created_at": mblog.get("created_at"),
                            "bid": mblog.get("bid"),
                            "mid": mblog.get("id"),
                        },
                    )
                )

                if len(results) >= max_results:
                    break
            except Exception as e:
                logger.debug("微博单条结果解析失败: %s", e)
                continue

        logger.info("微博返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_WEIBO,
            results=results,
            total_results=len(results),
        )
