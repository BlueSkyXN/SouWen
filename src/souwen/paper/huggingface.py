"""HuggingFace Papers API 客户端

官方端点: https://huggingface.co/api/papers/search?q={query}
鉴权: 无需 Key
限流: 宽松，无明确硬限制
返回: JSON（title, summary, id, upvotes）

文件用途：HuggingFace 每日精选论文搜索客户端，基于社区语义搜索，
包含 upvotes 字段作为社区热度信号。每篇论文均对应一篇 arXiv 论文。

参考来源：研究 https://github.com/jerpint/paperpal 项目，
         复现其 HuggingFace Papers 语义搜索能力，并整合进 SouWen 统一数据模型。

函数/类清单：
    HuggingFaceClient（类）
        - 功能：HuggingFace Papers 语义搜索客户端，解析 JSON 响应为统一数据模型
        - 关键属性：_client (SouWenHttpClient) HTTP 客户端, _limiter (TokenBucketLimiter)
                   限流器（5 req/s，保守设置）

    _parse_paper(paper: dict) -> PaperResult
        - 功能：将 HuggingFace API 返回的单篇论文 JSON 转换为 PaperResult
        - 输入：HuggingFace API 响应中单个 paper 对象（含 paper 子键）
        - 输出：统一的 PaperResult 模型，raw 中含 upvotes 和 arxiv_id

    search(query: str, top_n: int = 10) -> SearchResponse
        - 功能：使用 HuggingFace 语义搜索查找论文
        - 输入：query 搜索查询词（支持自然语言或关键词），top_n 返回数量
        - 输出：SearchResponse 包含结果列表及分页信息

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from souwen.core.exceptions import ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://huggingface.co"

# 保守限流：5 req/s
_DEFAULT_RPS = 5.0

_HF_PAPERS_URL = "https://huggingface.co/papers"


class HuggingFaceClient:
    """HuggingFace Papers 语义搜索客户端。

    特点:
        - 语义搜索（自然语言或关键词均可）
        - upvotes 字段反映社区热度，是独特的排名信号
        - 每篇论文均对应 arXiv，可获取 arxiv_id 和 PDF 链接
        - 无需 API Key，零配置即用
    """

    def __init__(self) -> None:
        """初始化 HuggingFace Papers 客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="huggingface")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> HuggingFaceClient:
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
    def _parse_paper(item: dict) -> PaperResult:
        """将 HuggingFace API 响应中的单篇论文转换为 PaperResult。

        HuggingFace 搜索 API 返回的顶层对象包含 "paper" 子键：
        {
            "paper": {
                "id": "2503.01469",          # arXiv ID
                "title": "...",
                "summary": "...",
                "upvotes": 42,
                "authors": [{"name": "..."}],
                ...
            }
        }

        Args:
            item: HuggingFace API 响应中的单条搜索结果（含 paper 子键）。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            paper = item.get("paper", item)

            arxiv_id: str = paper.get("id", "")
            title: str = paper.get("title", "")
            summary: str = paper.get("summary", "")
            upvotes: int = paper.get("upvotes", 0)

            # 作者解析：API 返回 [{"name": "..."}, ...]
            authors: list[Author] = []
            for author_item in paper.get("authors", []):
                name = (
                    author_item.get("name", "")
                    if isinstance(author_item, dict)
                    else str(author_item)
                )
                if name:
                    authors.append(Author(name=name))

            # 构建 URL
            source_url = f"{_HF_PAPERS_URL}/{arxiv_id}" if arxiv_id else _HF_PAPERS_URL
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None

            # 发表日期（HF API 提供 publishedAt 字段，格式 YYYY-MM-DDTHH:MM:SS.sssZ）
            published_at: str | None = paper.get("publishedAt")
            pub_date: str | None = None
            year: int | None = None
            if published_at:
                pub_date = published_at[:10]  # 取 YYYY-MM-DD
                try:
                    year = int(published_at[:4])
                except ValueError:
                    pass

            return PaperResult(
                title=title,
                authors=authors,
                abstract=summary,
                doi=None,
                year=year,
                publication_date=pub_date,
                source=SourceType.HUGGINGFACE,
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,  # HF 不提供引用数
                raw={
                    "arxiv_id": arxiv_id,
                    "upvotes": upvotes,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 HuggingFace paper 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_n: int = 10,
    ) -> SearchResponse:
        """使用 HuggingFace 语义搜索查找论文。

        HuggingFace 会自动判断是关键词搜索还是自然语言语义搜索，
        upvotes 字段反映社区热度，可作为额外排序/筛选信号。

        Args:
            query: 搜索查询词，支持自然语言或关键词。
            top_n: 返回结果数量（API 无严格上限，但建议 <= 50）。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        # HuggingFace 搜索端点：/api/papers/search?q=<query>
        encoded_query = quote(query, safe="")
        resp = await self._client.get(f"/api/papers/search?q={encoded_query}")
        data = resp.json()

        # API 返回列表，每项含 paper 子键
        if not isinstance(data, list):
            logger.warning("HuggingFace API 返回非预期格式: %s", type(data).__name__)
            data = []

        results: list[PaperResult] = []
        for item in data[:top_n]:
            try:
                results.append(self._parse_paper(item))
            except ParseError as exc:
                logger.debug("跳过解析失败的论文: %s", exc)

        return SearchResponse(
            query=query,
            total_results=len(results),
            page=1,
            per_page=top_n,
            results=results,
            source=SourceType.HUGGINGFACE,
        )
