"""DOAJ (Directory of Open Access Journals) API 客户端

官方端点: https://doaj.org/api/search/articles/{query}
鉴权: 可选 API Key (X-API-Key Header) — 无 Key 也可使用，仅影响限流
注册: https://doaj.org/account/register

文件用途：DOAJ 开放获取期刊文章搜索客户端，覆盖全球开放获取期刊
论文元数据。免费可用，无需 Key，配置 Key 后限流更宽松。

函数/类清单：
    DoajClient（类）
        - 功能：DOAJ 开放获取文章搜索客户端，解析 bibjson 响应为统一数据模型
        - 关键属性：api_key (str|None) 可选 API 密钥, _client (SouWenHttpClient)
                   HTTP 客户端, _limiter (TokenBucketLimiter) 令牌桶限流器
                   （有 Key 时 ~2 req/s，无 Key 时 ~1 req/s）

    _parse_result(item: dict) -> PaperResult
        - 功能：将 DOAJ API 返回的单条 bibjson 文章转换为统一 PaperResult
        - 输入：DOAJ API 响应中单条结果对象（含 bibjson 子键）
        - 输出：统一的 PaperResult 模型，raw 中保留 keywords、subject、issn 等

    search(query: str, page_size: int = 10, page: int = 1) -> SearchResponse
        - 功能：按关键词查询 DOAJ 文章索引
        - 输入：query 检索关键词, page_size 每页条数, page 当前页码
        - 输出：SearchResponse 包含结果列表、总数、分页信息

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - PaperResult, SearchResponse: 统一论文数据模型
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from souwen.config import get_config
from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://doaj.org/api"
_ARTICLE_URL = "https://doaj.org/article"

# 限流：有 Key 0.5s/req (2 rps)，无 Key 1.0s/req (1 rps)
_RPS_WITH_KEY = 2.0
_RPS_WITHOUT_KEY = 1.0


class DoajClient:
    """DOAJ 开放获取期刊文章搜索客户端。

    特点:
        - 完全开放获取的同行评议期刊文章
        - API Key 可选，未配置时仍可使用（限流更严）
        - 返回 bibjson 元数据，包含 DOI、ISSN、关键词、主题等
        - 不提供引用计数
    """

    def __init__(self, api_key: str | None = None) -> None:
        """初始化 DOAJ 客户端。

        Args:
            api_key: DOAJ API Key（可选）。未提供时从全局配置读取，
                     仍未配置则匿名访问，限流更严格。
        """
        cfg = get_config()
        self.api_key: str | None = api_key or cfg.resolve_api_key("doaj", "doaj_api_key")

        headers: dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        self._client = SouWenHttpClient(
            base_url=_BASE_URL,
            headers=headers,
            source_name="doaj",
        )
        rps = _RPS_WITH_KEY if self.api_key else _RPS_WITHOUT_KEY
        self._limiter = TokenBucketLimiter(rate=rps, burst=rps)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> DoajClient:
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
    def _parse_result(item: dict[str, Any]) -> PaperResult:
        """将 DOAJ 单条搜索结果转换为 PaperResult。

        DOAJ 响应结构：
        {
            "id": "...",
            "bibjson": {
                "title": "...",
                "author": [{"name": "..."}, ...],
                "abstract": "..." 或 {"text": "..."},
                "identifier": [{"type": "doi", "id": "10.xxx"}, ...],
                "year": "2024", "month": "3",
                "journal": {"title": "...", "issn": [...], ...},
                "keywords": [...],
                "subject": [{"term": "..."}, ...],
                "link": [{"type": "fulltext", "url": "..."}, ...]
            }
        }

        Args:
            item: DOAJ API 响应中的单条结果。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            bibjson: dict[str, Any] = item.get("bibjson", {}) or {}
            doaj_id: str = item.get("id", "")

            title: str = bibjson.get("title", "") or ""

            # 作者列表：[{"name": "..."}]
            authors: list[Author] = []
            for author_item in bibjson.get("author", []) or []:
                name = (
                    author_item.get("name", "")
                    if isinstance(author_item, dict)
                    else str(author_item)
                )
                if name:
                    authors.append(Author(name=name))

            # 摘要：可能是字符串，也可能是 {"text": "..."} 字典
            raw_abstract = bibjson.get("abstract")
            abstract: str | None = None
            if isinstance(raw_abstract, str):
                abstract = raw_abstract or None
            elif isinstance(raw_abstract, dict):
                abstract = raw_abstract.get("text") or None

            # DOI：在 identifier 列表中查找 type=="doi"
            doi: str | None = None
            for identifier in bibjson.get("identifier", []) or []:
                if isinstance(identifier, dict) and identifier.get("type", "").lower() == "doi":
                    doi = identifier.get("id")
                    break

            # 出版年/月
            year: int | None = None
            raw_year = bibjson.get("year")
            if raw_year:
                try:
                    year = int(str(raw_year)[:4])
                except (ValueError, TypeError):
                    pass

            pub_date: str | None = None
            raw_month = bibjson.get("month")
            if year:
                month_int = 1
                if raw_month:
                    try:
                        month_int = max(1, min(12, int(str(raw_month))))
                    except (ValueError, TypeError):
                        month_int = 1
                pub_date = f"{year:04d}-{month_int:02d}-01"

            # 期刊
            journal_obj = bibjson.get("journal") or {}
            journal_name: str | None = (
                journal_obj.get("title") if isinstance(journal_obj, dict) else None
            )

            # 链接：找 type=="fulltext"，按是否 .pdf 区分 pdf_url 和 source_url
            pdf_url: str | None = None
            fulltext_url: str | None = None
            for link in bibjson.get("link", []) or []:
                if not isinstance(link, dict):
                    continue
                if link.get("type", "").lower() != "fulltext":
                    continue
                url = link.get("url") or ""
                if not url:
                    continue
                if url.lower().endswith(".pdf"):
                    pdf_url = pdf_url or url
                else:
                    fulltext_url = fulltext_url or url

            # source_url：优先 fulltext 链接，否则用 DOAJ 文章页
            source_url: str = fulltext_url or (
                f"{_ARTICLE_URL}/{doaj_id}" if doaj_id else _ARTICLE_URL
            )

            # 主题：[{"term": "..."}]
            subjects: list[str] = []
            for subj in bibjson.get("subject", []) or []:
                if isinstance(subj, dict):
                    term = subj.get("term")
                    if term:
                        subjects.append(term)

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                journal=journal_name,
                source="doaj",  # type: ignore[arg-type]
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,  # DOAJ 不提供引用数
                raw={
                    "doaj_id": doaj_id,
                    "keywords": bibjson.get("keywords") or [],
                    "subject": subjects,
                    "issn": journal_obj.get("issn") if isinstance(journal_obj, dict) else None,
                    "publisher": journal_obj.get("publisher")
                    if isinstance(journal_obj, dict)
                    else None,
                    "country": journal_obj.get("country")
                    if isinstance(journal_obj, dict)
                    else None,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 DOAJ result 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        page_size: int = 10,
        page: int = 1,
    ) -> SearchResponse:
        """按关键词查询 DOAJ 文章索引。

        DOAJ 检索语法支持 Lucene 风格（field:value, AND/OR），
        简单关键词亦可。

        Args:
            query: 检索关键词或 Lucene 表达式。
            page_size: 每页条数。
            page: 当前页码（从 1 开始）。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        # DOAJ 将 query 直接编码到 URL path 中
        encoded_query = quote(query, safe="")
        path = f"/search/articles/{encoded_query}"
        params: dict[str, str | int] = {
            "page": page,
            "pageSize": page_size,
        }

        resp = await self._client.get(path, params=params)
        data: dict[str, Any] = resp.json()

        results_list = data.get("results", []) or []
        results: list[PaperResult] = []
        for item in results_list:
            try:
                results.append(self._parse_result(item))
            except ParseError as exc:
                logger.debug("跳过解析失败的 DOAJ 文章: %s", exc)

        return SearchResponse(
            query=query,
            total_results=data.get("total", len(results)),
            page=page,
            per_page=page_size,
            results=results,
            source="doaj",  # type: ignore[arg-type]
        )
