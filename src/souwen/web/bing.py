"""Bing 搜索引擎爬虫

文件用途：
    Bing 搜索引擎爬虫客户端。Bing 对爬虫的反爬检测相对宽松，
    是 Google 的可靠替代。通过 HTML 抓取获取搜索结果。

函数/类清单：
    BingClient（类）
        - 功能：Bing 搜索爬虫客户端，通过 HTML 解析获取搜索结果
        - 继承：BaseScraper（基础爬虫类）
        - 关键属性：ENGINE_NAME = "bing", BASE_URL = "https://www.bing.com/search",
                  min_delay = 1.5, max_delay = 4.0, max_retries = 3
        - 主要方法：search(query, max_results) -> WebSearchResponse

    BingClient.__init__(**kwargs)
        - 功能：初始化 Bing 搜索客户端
        - 输入：**kwargs 传递给 BaseScraper 的参数
        - 输出：实例

    BingClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：查询 Bing 搜索，返回聚合结果
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果

模块依赖：
    - logging: 日志记录
    - random: 随机选择请求头变体
    - secrets: 生成随机 MUID
    - urllib.parse: URL 编码与解析
    - bs4: HTML 解析
    - souwen.models: str, WebSearchResult, WebSearchResponse 数据模型
    - souwen.core.scraper.base: BaseScraper 基础爬虫类

技术要点：
    - 使用 CSS 选择器 li.b_algo 定位搜索结果容器
    - 标题优先 h2 > a，回退新版布局 .b_tpcn .tptt + a.tilk
    - Snippet 支持多选择器降级：div.b_caption p / .b_snippet / .b_lineclamp2 / .b_lineclamp3 / p
    - URL 必须是 http 开头（过滤相对路径），并跳过 Bing 内部跳转链接
    - 随机化 Accept-Language 和 MUID Cookie，规避反爬识别
    - 基于 URL 去重，避免重复结果
"""

from __future__ import annotations

import logging
import random
import secrets
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup

from souwen.models import WebSearchResult, WebSearchResponse
from souwen.core.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.bing")

_ACCEPT_LANGUAGE_VARIANTS = [
    "zh-CN,zh;q=0.9,en;q=0.8",
    "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "zh-CN,zh-Hans;q=0.9,zh;q=0.8,en;q=0.6",
]

# Bing redirect URL path prefixes to skip (tracking/redirect links)
_BING_REDIRECT_PREFIXES = ("/ck/a", "/newtabredir")


def _generate_muid() -> str:
    """生成随机 Bing MUID（Microsoft 用户标识），每次请求独立生成以模拟不同客户端"""
    return secrets.token_hex(16).upper()


def _build_bing_headers() -> dict[str, str]:
    """构建带随机化参数的 Bing 请求头（语言偏好 + 中文 Cookie）"""
    muid = _generate_muid()
    accept_language = random.choice(_ACCEPT_LANGUAGE_VARIANTS)
    return {
        "Accept-Language": accept_language,
        # SRCHHPGUSR=SRCHLANG=zh-Hans: 指定搜索语言为简体中文
        # _EDGE_S=ui=zh-cn: Edge 浏览器 UI 语言设置（中文大陆）
        # _EDGE_V=1: Edge 版本标识符，Bing 用于区分 Edge/Chrome 流量
        # MUID: Microsoft 用户 ID，每次请求随机生成，模拟不同客户端
        "Cookie": (f"SRCHHPGUSR=SRCHLANG=zh-Hans; _EDGE_S=ui=zh-cn; _EDGE_V=1; MUID={muid}"),
    }


class BingClient(BaseScraper):
    """Bing 搜索爬虫客户端

    Bing 反爬检测相对宽松，是 Google 的可靠替代。
    """

    ENGINE_NAME = "bing"
    BASE_URL = "https://www.bing.com/search"

    def __init__(self, **kwargs):
        # 初始化爬虫配置：最小延迟 1.5s、最大延迟 4.0s、最多重试 3 次
        super().__init__(min_delay=1.5, max_delay=4.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Bing

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        # URL 参数：q 搜索词，count 结果数（预留余量以应对过滤）
        url = f"{self._resolved_base_url}?q={quote_plus(query)}&count={min(max_results + 5, 50)}"

        resp = await self._fetch(url, headers=_build_bing_headers())
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []
        seen_urls: set[str] = set()

        try:
            # Bing 搜索结果容器：li.b_algo （有机结果）
            for element in soup.select("li.b_algo"):
                # 优先尝试标准布局 h2 > a，再尝试新版布局 .b_tpcn .tptt + a.tilk
                title_el = element.select_one("h2 a")
                raw_url = title_el.get("href", "") if title_el else ""
                title = title_el.get_text(strip=True) if title_el else ""

                if not title or not raw_url:
                    # 新版 Bing 布局回退：仅在缺少对应值时查询 DOM
                    if not title:
                        tptt_el = element.select_one(".b_tpcn .tptt")
                        if tptt_el:
                            title = tptt_el.get_text(strip=True)
                    if not raw_url:
                        tilk_el = element.select_one("a.tilk")
                        if tilk_el:
                            raw_url = tilk_el.get("href", "")
                            if not title:
                                title = tilk_el.get_text(strip=True)

                # 过滤非 HTTP 链接（相对路径等无效）
                if not raw_url or not raw_url.startswith("http"):
                    continue

                # 跳过 Bing 内部跳转追踪链接
                parsed_path = urlparse(raw_url).path
                if any(parsed_path.startswith(p) for p in _BING_REDIRECT_PREFIXES):
                    continue

                # URL 去重
                if raw_url in seen_urls:
                    continue
                seen_urls.add(raw_url)

                # 标题缺失时用域名作为兜底
                if not title:
                    title = urlparse(raw_url).hostname or raw_url

                # Snippet 提取：依次尝试多个选择器
                snippet = ""
                for sel in ["div.b_caption p", ".b_snippet", ".b_lineclamp2", ".b_lineclamp3", "p"]:
                    snippet_el = element.select_one(sel)
                    if snippet_el:
                        snippet = snippet_el.get_text(strip=True)
                        break

                if title and raw_url:
                    results.append(
                        WebSearchResult(
                            source="bing",
                            title=title,
                            url=str(raw_url),
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Bing HTML 解析失败: %s", e)

        logger.info("Bing 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="bing",
            results=results,
            total_results=len(results),
        )
