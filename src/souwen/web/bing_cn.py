"""必应中文搜索（cn.bing.com）爬虫

文件用途：
    必应中文搜索引擎爬虫客户端。使用 cn.bing.com 端点，针对中文搜索优化，
    结果偏向中文内容，无需 API Key，支持分页偏移。

    与 BingClient（www.bing.com）的核心差异：
    1. 端点：使用 cn.bing.com（中文必应，结果更偏向中文内容）
    2. 分页参数：使用 first={offset+1} 参数控制起始位置（1-based），
               支持真正的翻页，同时通过 count 参数控制每页返回数量
    3. 语言头：显式设置 Accept-Language: zh-CN,zh;q=0.9 强制返回中文结果

函数/类清单：
    BingCnClient（类）
        - 功能：必应中文搜索爬虫客户端，通过 HTML 解析获取中文搜索结果
        - 继承：BaseScraper（基础爬虫类）
        - 关键属性：ENGINE_NAME = "bing_cn", BASE_URL = "https://cn.bing.com/search",
                  min_delay = 1.5, max_delay = 4.0, max_retries = 3
        - 主要方法：search(query, max_results, offset) -> WebSearchResponse

模块依赖：
    - logging: 日志记录
    - urllib.parse: URL 编码/解码
    - base64: 解码 Bing 重定向 URL
    - bs4: HTML 解析
    - souwen.models: str, WebSearchResult, WebSearchResponse 数据模型
    - souwen.core.scraper.base: BaseScraper 基础爬虫类

技术要点：
    - 使用 CSS 选择器 li.b_algo 定位搜索结果容器
    - 标题在 h2 > a，snippet 在 div.b_caption p 或 p
    - 使用 first + count 参数实现分页偏移 + 返回数量控制
    - Accept-Language 头强制返回中文结果
    - 自动解析 bing.com/ck/a 重定向 URL 获取真实目标地址
    - 检测验证码/阻断页面并记录警告
"""

from __future__ import annotations

import base64
import logging
from urllib.parse import parse_qs, quote_plus, urlparse

from bs4 import BeautifulSoup

from souwen.models import WebSearchResult, WebSearchResponse
from souwen.core.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.bing_cn")

# 强制中文结果的 Accept-Language 头
_ZH_LANGUAGE_HEADER = {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}

# Bing 验证/阻断页面的典型标记
_BLOCK_MARKERS = ("验证", "Verify", "/fd/ls/lsp.aspx", "captcha")


def _resolve_bing_redirect(url: str) -> str:
    """解析 Bing 的 /ck/a 重定向 URL，提取真实目标地址

    Bing 经常将结果链接包装为 https://www.bing.com/ck/a?...&u=a1<base64>&...
    其中 u 参数是 "a1" + base64url 编码的真实 URL。
    """
    if "/ck/a" not in url:
        return url
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        u_values = params.get("u", [])
        if u_values:
            encoded = u_values[0]
            # 去除 "a1" 前缀
            if encoded.startswith("a1"):
                encoded = encoded[2:]
            # base64url 解码（补齐 padding）
            padding = 4 - len(encoded) % 4
            if padding != 4:
                encoded += "=" * padding
            decoded = base64.urlsafe_b64decode(encoded).decode("utf-8", errors="replace")
            if decoded.startswith("http"):
                return decoded
    except Exception:
        pass
    return url


class BingCnClient(BaseScraper):
    """必应中文搜索爬虫客户端

    使用 cn.bing.com 端点，结果偏向中文内容。
    与 BingClient 相比，主要差异在于端点、分页参数和语言头设置。
    支持通过 offset 参数实现真正的翻页。
    """

    ENGINE_NAME = "bing_cn"
    BASE_URL = "https://cn.bing.com/search"

    def __init__(self, **kwargs):
        super().__init__(min_delay=1.5, max_delay=4.0, max_retries=3, **kwargs)

    async def search(
        self,
        query: str,
        max_results: int = 20,
        offset: int = 0,
    ) -> WebSearchResponse:
        """搜索必应中文（cn.bing.com）

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            offset: 结果偏移量（0 表示从第 1 条结果开始），用于翻页

        Returns:
            WebSearchResponse 包含搜索结果
        """
        # first: 起始位置（1-based），count: 请求数量（多请求一些以防过滤损失）
        count = min(max_results + 5, 50)
        url = f"{self._resolved_base_url}?q={quote_plus(query)}&first={offset + 1}&count={count}"

        resp = await self._fetch(url, headers=_ZH_LANGUAGE_HEADER)
        html = resp.text

        # 检测验证码/阻断页面
        if not any(marker in html for marker in ("b_algo", "b_results")):
            if any(marker in html for marker in _BLOCK_MARKERS):
                logger.warning("必应中文 检测到验证码/阻断页面 (query=%s)", query)
                return WebSearchResponse(
                    query=query,
                    source="bing_cn",
                    results=[],
                    total_results=0,
                )

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            for element in soup.select("li.b_algo"):
                title_el = element.select_one("h2 a")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)
                raw_url = title_el.get("href", "")

                if not title or not raw_url or not raw_url.startswith("http"):
                    continue

                # 解析 Bing 重定向 URL 获取真实目标地址
                resolved_url = _resolve_bing_redirect(str(raw_url))

                # Snippet 提取
                snippet = ""
                for sel in ["div.b_caption p", "p"]:
                    snippet_el = element.select_one(sel)
                    if snippet_el:
                        snippet = snippet_el.get_text(strip=True)
                        break

                results.append(
                    WebSearchResult(
                        source="bing_cn",
                        title=title,
                        url=resolved_url,
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                    )
                )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("必应中文 HTML 解析失败: %s", e)

        logger.info("必应中文 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="bing_cn",
            results=results,
            total_results=len(results),
        )
