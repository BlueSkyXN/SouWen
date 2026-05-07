"""DuckDuckGo 网页文本搜索引擎

使用 html.duckduckgo.com POST 接口实现网页搜索。
支持区域、安全搜索、时间范围过滤及多页分页。

技术方案：
    - POST 表单提交搜索（html 后端）
    - 分页：echo 服务端返回的 hidden form inputs
    - TLS 指纹模拟 via BaseScraper (curl_cffi)
    - 禁用 follow_redirects（301 = 反爬信号）
    - 多模式 no-results 检测
"""

from __future__ import annotations

import logging
from html import unescape

from lxml import html as lxml_html

from souwen.models import WebSearchResult, WebSearchResponse
from souwen.core.scraper.base import BaseScraper
from souwen.web.ddg_utils import normalize_url, normalize_text, parse_next_form_data

logger = logging.getLogger("souwen.web.duckduckgo")

# DDG 的 "无结果" 标记 — html 后端用两个空格
_NO_RESULTS_HTML = b"No  results."
_NO_RESULTS_LITE = b"No more results."

# 广告 URL 前缀 — 需要过滤
_AD_PREFIXES = (
    "http://www.google.com/search?q=",
    "https://duckduckgo.com/y.js?ad_domain",
)


class DuckDuckGoClient(BaseScraper):
    """DuckDuckGo 网页搜索客户端

    通过 POST 提交搜索并解析 HTML 结果。
    支持区域、安全搜索、时间范围、分页。
    TLS 指纹模拟 + 自适应退避。
    """

    ENGINE_NAME = "duckduckgo"
    BASE_URL = "https://html.duckduckgo.com/html/"

    def __init__(self, **kwargs):
        super().__init__(
            min_delay=0.75,
            max_delay=1.5,
            max_retries=3,
            follow_redirects=False,
            **kwargs,
        )

    async def search(
        self,
        query: str,
        max_results: int = 20,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        time_range: str | None = None,
        max_pages: int = 3,
    ) -> WebSearchResponse:
        """搜索 DuckDuckGo 网页

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            region: 区域代码，如 "wt-wt"(全球), "us-en", "cn-zh"
            safesearch: 安全搜索级别 "on"/"moderate"/"off"
            time_range: 时间范围 "d"(天)/"w"(周)/"m"(月)/"y"(年)/None
            max_pages: 最大分页数（默认 3）

        Returns:
            WebSearchResponse 包含搜索结果
        """
        results: list[WebSearchResult] = []
        seen_urls: set[str] = set()

        # 首次请求的 form data
        form_data: dict[str, str] = {
            "q": query,
            "b": "",
            "kl": region,
        }
        if time_range:
            form_data["df"] = time_range

        url = self._resolved_base_url

        for page in range(max_pages):
            try:
                resp = await self._fetch(url, method="POST", data=form_data)

                # 301/302/202/403 = DDG 反爬信号
                if resp.status_code in (301, 302, 202, 403, 418):
                    logger.warning("DDG 反爬响应 status=%d，停止分页", resp.status_code)
                    break

                if resp.status_code != 200:
                    logger.warning("DDG 异常状态码 %d", resp.status_code)
                    break

                content = resp.content if hasattr(resp, "content") else resp.text.encode()

                # 检测 no-results 标记
                if _NO_RESULTS_HTML in content or _NO_RESULTS_LITE in content:
                    break

                # 解析结果
                page_results = self._parse_html_results(content, seen_urls)
                results.extend(page_results)

                if len(results) >= max_results:
                    results = results[:max_results]
                    break

                # 没有解析出任何结果 → 可能被阻断
                if not page_results:
                    break

                # 提取分页 form data
                next_data = parse_next_form_data(content)
                if not next_data:
                    break
                form_data = next_data

            except Exception as e:
                logger.warning("DDG 第 %d 页请求失败: %s", page + 1, e)
                break

        logger.info("DuckDuckGo 返回 %d 条结果 (query=%s)", len(results), query)
        return WebSearchResponse(
            query=query,
            source="duckduckgo",
            results=results,
            total_results=len(results),
        )

    def _parse_html_results(self, content: bytes, seen_urls: set[str]) -> list[WebSearchResult]:
        """解析 DuckDuckGo HTML 搜索结果页"""
        results: list[WebSearchResult] = []

        try:
            tree = lxml_html.fromstring(content)
        except Exception as e:
            logger.warning("HTML 解析失败: %s", e)
            return results

        # html 后端: div[h2] 格式
        for div in tree.xpath("//div[h2]"):
            try:
                # 标题 + href — 仅从 h2 内的 a 提取
                anchors = div.xpath("./h2/a/@href")
                if not anchors:
                    anchors = div.xpath("./a/@href")
                titles = div.xpath("./h2/a//text()")
                if not anchors or not titles:
                    continue

                raw_url = anchors[0]
                title = unescape("".join(t.strip() for t in titles if t.strip()))

                # 跳过广告
                if any(raw_url.startswith(p) for p in _AD_PREFIXES):
                    continue

                real_url = normalize_url(self._decode_ddg_url(str(raw_url)))
                if not real_url.startswith(("http://", "https://")):
                    continue

                if real_url in seen_urls:
                    continue
                seen_urls.add(real_url)

                # 描述文本
                body_parts = div.xpath(".//a[@class='result__snippet']//text()")
                if not body_parts:
                    body_parts = div.xpath(".//td[@class='result-snippet']//text()")
                if not body_parts:
                    body_parts = div.xpath(".//a[contains(@class,'snippet')]//text()")
                snippet = normalize_text(" ".join(body_parts)) if body_parts else ""

                if title:
                    results.append(
                        WebSearchResult(
                            source="duckduckgo",
                            title=title,
                            url=real_url,
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )
            except Exception:
                continue

        return results

    @staticmethod
    def _decode_ddg_url(url: str) -> str:
        """解码 DuckDuckGo 重定向 URL

        DuckDuckGo 通过 //duckduckgo.com/l/?uddg=ENCODED_URL 跳转。
        """
        from urllib.parse import unquote as _unquote

        if "uddg=" in url:
            parts = url.split("uddg=", 1)
            if len(parts) > 1:
                encoded = parts[1].split("&", 1)[0]
                return _unquote(encoded)
        return url
