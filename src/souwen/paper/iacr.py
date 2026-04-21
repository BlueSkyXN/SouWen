"""IACR ePrint Archive 搜索客户端

官方文档: https://eprint.iacr.org/
鉴权: 无需 Key
限流: 建议 1 req/s
返回: JSON（通过 IACR 搜索 API）

文件用途：IACR ePrint Archive 密码学预印本搜索客户端，
涵盖密码学、信息安全、隐私保护等领域论文。

函数/类清单：
    IacrClient（类）
        - 功能：IACR ePrint Archive 搜索客户端，调用 /search 端点获取 JSON 结果
        - 关键属性：_client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（1 req/s）

    _parse_paper(item: dict) -> PaperResult
        - 功能：将 IACR 搜索结果 JSON 条目转换为 PaperResult
        - 输入：item IACR 搜索 API 返回的单条论文 JSON
        - 输出：统一的 PaperResult 模型

    search(query: str, max_results: int) -> SearchResponse
        - 功能：在 IACR ePrint 中搜索密码学论文
        - 输入：query 检索词，max_results 返回条数上限
        - 输出：SearchResponse 包含结果列表

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://eprint.iacr.org"

# 保守限流：每秒 1 次
_RATE_LIMIT_RPS = 1.0


class IacrClient:
    """IACR ePrint Archive 密码学预印本搜索客户端。

    通过 IACR 搜索 API 检索密码学、零知识证明、密码协议等领域论文。
    所有论文均可免费下载 PDF。
    """

    def __init__(self) -> None:
        """初始化 IACR 客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="iacr")
        self._limiter = TokenBucketLimiter(rate=_RATE_LIMIT_RPS, burst=1.0)

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
    def _parse_paper(item: dict[str, Any]) -> PaperResult:
        """将 IACR 搜索结果条目转换为 PaperResult。

        Args:
            item: IACR 搜索 API 返回的单条论文 JSON 对象。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            title = (item.get("title") or "").strip()
            abstract = (item.get("abstract") or "").strip() or None

            # 论文编号格式：YYYY/NNN，如 "2024/001"
            paper_id = item.get("id") or item.get("number") or ""

            # 作者列表（字符串列表或逗号分隔字符串）
            authors: list[Author] = []
            raw_authors = item.get("authors") or []
            if isinstance(raw_authors, list):
                for name in raw_authors:
                    name = (name or "").strip()
                    if name:
                        authors.append(Author(name=name))
            elif isinstance(raw_authors, str):
                for name in raw_authors.split(","):
                    name = name.strip()
                    if name:
                        authors.append(Author(name=name))

            # 发表年份（从 paper_id 或独立字段提取）
            year: int | None = None
            pub_date: str | None = None
            year_str = item.get("year") or (paper_id.split("/")[0] if "/" in paper_id else "")
            if year_str:
                try:
                    year = int(year_str)
                    pub_date = f"{year}-01-01"
                except ValueError:
                    pass

            # 构建 IACR 论文 URL 和 PDF 链接
            if paper_id:
                source_url = f"https://eprint.iacr.org/{paper_id}"
                pdf_url = f"https://eprint.iacr.org/{paper_id}.pdf"
            else:
                source_url = "https://eprint.iacr.org/"
                pdf_url = None

            # DOI（部分 IACR 论文有 DOI）
            doi = item.get("doi") or None

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=SourceType.IACR,
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,
                raw={
                    "paper_id": paper_id,
                    "keywords": item.get("keywords"),
                    "note": item.get("note"),
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 IACR 论文失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> SearchResponse:
        """在 IACR ePrint Archive 中搜索密码学论文。

        Args:
            query: 检索词（标题、摘要、作者均参与匹配）。
            max_results: 返回条数上限。

        Returns:
            SearchResponse 包含结果列表。
        """
        await self._limiter.acquire()

        params: dict[str, Any] = {
            "q": query,
            "action": "search",
        }

        resp = await self._client.get("/search", params=params)

        # IACR /search 端点返回 JSON 数组或含 papers 键的对象
        try:
            data: Any = resp.json()
        except Exception as exc:
            raise ParseError(f"IACR JSON 解析失败: {exc}") from exc

        # 兼容多种响应格式
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (
                data.get("papers")
                or data.get("results")
                or data.get("hits")
                or []
            )
        else:
            items = []

        results: list[PaperResult] = []
        for item in items[:max_results]:
            try:
                results.append(self._parse_paper(item))
            except ParseError as exc:
                logger.warning("跳过解析失败的 IACR 论文: %s", exc)

        return SearchResponse(
            query=query,
            total_results=len(items),
            page=1,
            per_page=max_results,
            results=results,
            source=SourceType.IACR,
        )
