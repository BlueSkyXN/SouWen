"""bioRxiv Content API 客户端

官方文档: https://api.biorxiv.org/
鉴权: 无需 Key
限流: 无硬限制，建议 1 req/s
返回: JSON

文件用途：bioRxiv 预印本搜索客户端，基于日期范围获取生物科学领域预印本。
bioRxiv API 不支持关键词搜索，仅支持按日期区间或 DOI 检索。

函数/类清单：
    BiorxivClient（类）
        - 功能：bioRxiv Content API v2 客户端，支持按日期范围批量获取最新预印本
        - 关键属性：_client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（1 req/s）

    _parse_item(item: dict) -> PaperResult
        - 功能：将 bioRxiv API 返回的单条 JSON 对象转换为 PaperResult
        - 输入：item bioRxiv collection 数组中的单个条目
        - 输出：统一的 PaperResult 模型，包含 DOI、作者、类别等字段

    search(query: str, max_results: int, days: int) -> SearchResponse
        - 功能：获取最近 days 天内的 bioRxiv 预印本
        - 说明：bioRxiv 无关键词搜索 API，query 参数仅用于元数据记录（不作过滤）
        - 输入：query 记录用查询词（不做服务端过滤），max_results 返回条数，
               days 回溯天数（默认 30）
        - 输出：SearchResponse 包含结果列表

    search_by_date(start_date: str, end_date: str, max_results: int) -> SearchResponse
        - 功能：按精确日期范围检索 bioRxiv 预印本
        - 输入：start_date/end_date YYYY-MM-DD 格式，max_results 返回条数上限
        - 输出：SearchResponse 包含结果列表

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.biorxiv.org"

# 保守限流：每秒 1 次
_RATE_LIMIT_RPS = 1.0


class BiorxivClient:
    """bioRxiv 预印本搜索客户端。

    bioRxiv Content API v2 仅支持按日期范围或 DOI 获取论文，
    不支持关键词搜索。search() 方法默认返回最近 N 天的预印本。
    """

    # 子类可覆盖为 "medrxiv" 以复用相同逻辑
    _SERVER: str = "biorxiv"
    _SOURCE_TYPE: SourceType = SourceType.BIORXIV

    def __init__(self) -> None:
        """初始化 bioRxiv 客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name=self._SERVER)
        self._limiter = TokenBucketLimiter(rate=_RATE_LIMIT_RPS, burst=1.0)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> BiorxivClient:
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

    def _parse_item(self, item: dict[str, Any]) -> PaperResult:
        """将 bioRxiv collection 条目转换为 PaperResult。

        Args:
            item: bioRxiv API 返回的单条论文 JSON。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            title = (item.get("title") or "").strip()
            doi = item.get("doi") or None
            abstract = (item.get("abstract") or "").strip() or None

            # 作者字段为逗号分隔的姓名字符串
            author_str = item.get("authors") or ""
            authors: list[Author] = []
            for name in author_str.split(";"):
                name = name.strip()
                if name:
                    authors.append(Author(name=name))

            # 发表日期
            pub_date = item.get("date") or None  # 格式：YYYY-MM-DD

            year: int | None = None
            if pub_date:
                try:
                    year = int(pub_date[:4])
                except (ValueError, IndexError):
                    pass

            category = item.get("category") or None
            server = item.get("server") or self._SERVER

            # 构建论文 URL：https://www.biorxiv.org/content/{doi}
            if doi:
                source_url = f"https://www.{server}.org/content/{doi}"
                pdf_url = f"https://www.{server}.org/content/{doi}.full.pdf"
            else:
                source_url = f"https://www.{server}.org/"
                pdf_url = None

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=self._SOURCE_TYPE,
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,
                raw={
                    "category": category,
                    "server": server,
                    "jatsxml": item.get("jatsxml"),
                    "published": item.get("published"),
                    "type": item.get("type"),
                    "license": item.get("license"),
                    "author_corresponding": item.get("author_corresponding"),
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 {self._SERVER} 条目失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search_by_date(
        self,
        start_date: str,
        end_date: str,
        max_results: int = 10,
    ) -> SearchResponse:
        """按日期范围检索预印本。

        Args:
            start_date: 起始日期，格式 ``YYYY-MM-DD``。
            end_date: 结束日期，格式 ``YYYY-MM-DD``。
            max_results: 返回条数上限，API 单页最多 100 条。

        Returns:
            SearchResponse 包含结果列表。
        """
        await self._limiter.acquire()

        # cursor=0 表示从第一条开始；API 按最新排序
        url = f"/details/{self._SERVER}/{start_date}/{end_date}/0/json"
        resp = await self._client.get(url)

        try:
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            raise ParseError(f"{self._SERVER} JSON 解析失败: {exc}") from exc

        messages = data.get("messages", [])
        total: int = 0
        if messages:
            try:
                total = int(messages[0].get("total", 0))
            except (ValueError, TypeError):
                pass

        collection: list[dict[str, Any]] = data.get("collection", [])
        results: list[PaperResult] = []
        for item in collection[:max_results]:
            try:
                results.append(self._parse_item(item))
            except ParseError as exc:
                logger.warning("跳过解析失败的 %s 条目: %s", self._SERVER, exc)

        return SearchResponse(
            query=f"{start_date}/{end_date}",
            total_results=total or len(results),
            page=1,
            per_page=max_results,
            results=results,
            source=self._SOURCE_TYPE,
        )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        days: int = 30,
    ) -> SearchResponse:
        """获取最近 days 天内的预印本。

        bioRxiv 无关键词搜索 API，本方法返回指定时间段内的最新预印本。
        query 参数仅记录于 SearchResponse.query，不做服务端过滤。

        Args:
            query: 查询词（仅记录用，不做过滤）。
            max_results: 返回条数上限。
            days: 向前回溯天数，默认 30 天。

        Returns:
            SearchResponse 包含结果列表。
        """
        end = date.today()
        start = end - timedelta(days=days)
        resp = await self.search_by_date(
            start.isoformat(),
            end.isoformat(),
            max_results=max_results,
        )
        # 用原始 query 覆盖日期区间 query，便于上层追踪
        return SearchResponse(
            query=query,
            total_results=resp.total_results,
            page=resp.page,
            per_page=resp.per_page,
            results=resp.results,
            source=self._SOURCE_TYPE,
        )
