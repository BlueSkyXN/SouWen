"""IACR ePrint 密码学预印本搜索客户端（实验性 HTML 爬虫）

官方端点: https://eprint.iacr.org/search?q={query}
鉴权: 无需 Key
限流: 0.5 req/s（保守，避免对学术小站造成压力）
返回: HTML 页面（使用 BeautifulSoup4 + lxml 解析）

文件用途：
    国际密码学研究协会 (IACR) ePrint 预印本归档搜索客户端。
    密码学领域权威预印本来源，covers crypto / security / theory 等方向。
    属于 **实验性 (experimental)** 数据源——通过 HTML 抓取实现，
    一旦 IACR 调整页面结构（CSS class / DOM 层级）即可能失效。

设计要点：
    - 仅请求一次搜索页，不再二次抓取每篇论文详情，节省请求配额。
    - 解析容错：单个结果块解析失败时跳过，不影响整体响应。
    - paper_id 形如 "2025/1014"，年份直接来自路径段第一段。

函数/类清单：
    IacrClient（类）
        - 功能：IACR ePrint 搜索客户端（实验性，HTML 抓取）
        - 关键属性：_client (SouWenHttpClient), _limiter (TokenBucketLimiter, 0.5 rps)

    _parse_result_block(block) -> PaperResult | None
        - 功能：解析单个搜索结果 HTML 块为 PaperResult，失败返回 None
        - 输入：BeautifulSoup Tag / NavigableString
        - 输出：PaperResult 或 None（解析失败时静默跳过）

    search(query: str, max_results: int = 10) -> SearchResponse
        - 功能：搜索 IACR ePrint 归档
        - 输入：query 关键词，max_results 最大返回数
        - 输出：SearchResponse 包含 PaperResult 列表

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - bs4 / lxml: HTML 解析
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://eprint.iacr.org"

# 保守限流：0.5 req/s（学术小站，避免造成负担）
_DEFAULT_RPS = 0.5

# 论文 ID 形如 "2025/1014"，用于从 href 中提取
_PAPER_ID_RE = re.compile(r"/?(\d{4}/\d+)")

# 多作者拆分：先按 " and " 再按 ","
_AUTHOR_AND_RE = re.compile(r"\s+and\s+", re.IGNORECASE)


class IacrClient:
    """IACR ePrint 密码学预印本搜索客户端（实验性）。

    特点:
        - 无需 API Key，零配置即用
        - 密码学 / 安全 / 理论领域的权威预印本来源
        - 通过 HTML 抓取实现，**实验性**——页面结构变更时可能失效
        - 不二次抓取详情页，所有字段从搜索结果块解析

    Warning:
        实验性数据源。IACR 调整页面 CSS / DOM 时本客户端可能停止工作，
        请定期校验 selectors 与抽取逻辑。
    """

    def __init__(self) -> None:
        """初始化 IACR ePrint 搜索客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="iacr")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=1)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> IacrClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _split_authors(raw: str) -> list[Author]:
        """拆分作者字符串为 Author 列表，先按 ' and ' 再按 ','。"""
        if not raw:
            return []
        parts: list[str] = []
        for chunk in _AUTHOR_AND_RE.split(raw):
            parts.extend(p.strip() for p in chunk.split(",") if p.strip())
        return [Author(name=name) for name in parts if name]

    @staticmethod
    def _extract_paper_id(block: Any) -> str | None:
        """从结果块中提取 paper_id（形如 '2025/1014'）。

        优先匹配 a.paperlink，否则回退扫描所有 <a> 标签。
        """
        anchor = block.select_one("a.paperlink")
        if anchor and anchor.get("href"):
            match = _PAPER_ID_RE.search(anchor["href"])
            if match:
                return match.group(1)

        for a in block.find_all("a", href=True):
            match = _PAPER_ID_RE.search(a["href"])
            if match:
                return match.group(1)
        return None

    @classmethod
    def _parse_result_block(cls, block: Any) -> PaperResult | None:
        """将单个搜索结果 HTML 块解析为 PaperResult。

        Args:
            block: BeautifulSoup Tag，对应一个 div.mb-4 结果容器。

        Returns:
            PaperResult；若关键字段（paper_id / title）缺失则返回 None。
        """
        try:
            paper_id = cls._extract_paper_id(block)
            if not paper_id:
                return None

            # 标题：第一个 <strong>
            title_tag = block.find("strong")
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                # 退化方案：使用 paperlink 锚点文本
                anchor = block.select_one("a.paperlink")
                if anchor:
                    title = anchor.get_text(strip=True)
            if not title:
                return None

            # 作者
            authors_tag = block.select_one("span.fst-italic")
            authors: list[Author] = []
            if authors_tag:
                authors = cls._split_authors(authors_tag.get_text(" ", strip=True))

            # 摘要
            abstract_tag = block.select_one("p.search-abstract")
            abstract: str | None = None
            if abstract_tag:
                abstract = abstract_tag.get_text(" ", strip=True) or None

            # 类别 / 主题（可能多个 badge）
            badges = block.select("small.badge")
            categories = [b.get_text(strip=True) for b in badges if b.get_text(strip=True)]
            venue: str | None = ", ".join(categories) if categories else None

            # 最近更新日期文本（可选信息，留存于 raw）
            updated_tag = block.select_one("small.ms-auto")
            last_updated = updated_tag.get_text(strip=True) if updated_tag else None

            # 年份从 paper_id 前 4 位提取
            year: int | None = None
            try:
                year = int(paper_id.split("/", 1)[0])
            except (ValueError, IndexError):
                year = None

            source_url = f"{_BASE_URL}/{paper_id}"
            pdf_url = f"{_BASE_URL}/{paper_id}.pdf"

            return PaperResult(
                source=SourceType.IACR,
                title=title,
                authors=authors,
                abstract=abstract,
                doi=None,
                year=year,
                publication_date=None,
                venue=venue,
                citation_count=None,
                source_url=source_url,
                pdf_url=pdf_url,
                raw={
                    "paper_id": paper_id,
                    "categories": categories,
                    "last_updated": last_updated,
                },
            )
        except Exception as exc:
            logger.debug("IACR 单条结果解析失败，跳过: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> SearchResponse:
        """搜索 IACR ePrint 密码学预印本归档。

        Note:
            **实验性数据源**：本方法通过 HTML 抓取实现。
            如果 IACR 调整页面结构（CSS class / DOM 层级），结果可能为空或异常。

        Args:
            query: 搜索关键词。
            max_results: 最大返回结果数。

        Returns:
            SearchResponse 包含 PaperResult 列表。
        """
        await self._limiter.acquire()

        encoded_query = quote(query, safe="")
        resp = await self._client.get(f"/search?q={encoded_query}")

        soup = BeautifulSoup(resp.text, "lxml")

        # 主选择器：div.mb-4。若未命中，回退为含 a.paperlink 的最近祖先 div。
        blocks = soup.select("div.mb-4")
        if not blocks:
            anchors = soup.select("a.paperlink")
            seen: set[int] = set()
            blocks = []
            for a in anchors:
                parent = a.find_parent("div")
                if parent is not None and id(parent) not in seen:
                    seen.add(id(parent))
                    blocks.append(parent)

        results: list[PaperResult] = []
        for block in blocks:
            if len(results) >= max_results:
                break
            paper = self._parse_result_block(block)
            if paper:
                results.append(paper)

        return SearchResponse(
            query=query,
            total_results=len(results),
            page=1,
            per_page=max_results,
            results=results,
            source=SourceType.IACR,
        )
