"""HAL (Hyper Articles en Ligne) API 客户端

官方端点: https://api.archives-ouvertes.fr/search/
鉴权: 无需 Key
限流: 宽松，无明确硬限制（保守 5 req/s）
返回: JSON（Solr 响应，多数字段为数组）

文件用途：HAL 法国开放档案搜索客户端，覆盖法国及国际机构的论文、
            预印本、博士论文等开放获取学术成果，基于 Solr 检索引擎。

参考来源：HAL 官方 API 文档 https://api.archives-ouvertes.fr/docs/search

函数/类清单：
    HalClient（类）
        - 功能：HAL Solr 检索客户端，解析 JSON 响应为统一数据模型
        - 关键属性：_client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（5 req/s）

    _parse_doc(doc: dict) -> PaperResult
        - 功能：将 HAL Solr 返回的单条 doc 转换为 PaperResult
        - 输入：HAL response.docs 中的单条文献对象
        - 输出：统一的 PaperResult 模型
        - 注意：HAL 多数字段为数组（含 title_s/abstract_s），均取第一个元素

    search(query: str, rows: int = 10) -> SearchResponse
        - 功能：使用 Solr 查询语法搜索 HAL 文献库
        - 输入：query Solr 查询串, rows 返回条数
        - 输出：SearchResponse 包含结果列表及分页信息

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - PaperResult, SourceType: 统一论文数据模型
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.archives-ouvertes.fr"

# 保守限流：5 req/s
_DEFAULT_RPS = 5.0

# 需要返回的 Solr 字段（fl 参数）
_FIELDS = ",".join(
    [
        "halId_s",
        "title_s",
        "authFullName_s",
        "abstract_s",
        "doiId_s",
        "producedDateY_i",
        "submittedDate_s",
        "linkExtUrl_s",
        "fileMain_s",
        "uri_s",
        "docType_s",
        "journalTitle_s",
    ]
)


def _first(value: Any) -> Any:
    """HAL Solr 多数字段为数组，统一取首元素。

    Args:
        value: 任意值（可能是 list / 标量 / None）。

    Returns:
        若为非空 list 返回第一个元素；否则原样返回。
    """
    if isinstance(value, list):
        return value[0] if value else None
    return value


class HalClient:
    """HAL 法国开放档案检索客户端。

    特点:
        - 基于 Solr，支持丰富的查询语法（字段限定、布尔、范围等）
        - 字段以后缀标识类型：_s 字符串、_i 整数、_t 文本
        - 无需 API Key，零配置即用
        - fileMain_s 直接给出 PDF URL
    """

    def __init__(self) -> None:
        """初始化 HAL 客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="hal")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> HalClient:
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
    def _parse_doc(doc: dict[str, Any]) -> PaperResult:
        """将 HAL Solr response.docs 中的单条记录转换为 PaperResult。

        Args:
            doc: HAL Solr 响应中的单条文献对象。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            hal_id: str = _first(doc.get("halId_s")) or ""
            title: str = _first(doc.get("title_s")) or ""
            abstract: str = _first(doc.get("abstract_s")) or ""

            # 作者：authFullName_s 已是全名列表
            raw_authors = doc.get("authFullName_s") or []
            if isinstance(raw_authors, str):
                raw_authors = [raw_authors]
            authors: list[Author] = [
                Author(name=name) for name in raw_authors if name and isinstance(name, str)
            ]

            # DOI：HAL 中通常已是字符串，少数情况下也可能为列表
            doi_raw = doc.get("doiId_s")
            doi: str | None = _first(doi_raw) if isinstance(doi_raw, list) else doi_raw
            if doi == "":
                doi = None

            # 年份：producedDateY_i 是整数年份
            year_raw = doc.get("producedDateY_i")
            year: int | None
            if isinstance(year_raw, list):
                year_raw = year_raw[0] if year_raw else None
            try:
                year = int(year_raw) if year_raw is not None else None
            except (TypeError, ValueError):
                year = None

            # 提交日期：submittedDate_s 形如 "2024-01-15 10:00:00" 或 ISO 字符串
            submitted = _first(doc.get("submittedDate_s"))
            pub_date: str | None = None
            if isinstance(submitted, str) and submitted:
                # 取前 10 位（YYYY-MM-DD）即可，PaperResult 校验器会容错处理
                text = submitted.replace("T", " ")
                pub_date = text[:10]

            # PDF：fileMain_s 是直接 PDF URL（可能为字符串或数组）
            pdf_url = _first(doc.get("fileMain_s"))
            if pdf_url == "":
                pdf_url = None

            # 源 URL：优先 uri_s（HAL 详情页），缺失时基于 halId 构造
            uri = _first(doc.get("uri_s"))
            if uri:
                source_url = uri
            elif hal_id:
                source_url = f"https://hal.science/{hal_id}"
            else:
                source_url = "https://hal.science/"

            # 期刊：journalTitle_s 多为字符串
            journal = _first(doc.get("journalTitle_s")) or None

            # 外部链接（用于 raw 调试参考）
            ext_links = doc.get("linkExtUrl_s")
            if isinstance(ext_links, str):
                ext_links = [ext_links]

            doc_type = _first(doc.get("docType_s"))

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=SourceType.HAL,
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,  # HAL 不提供引用数
                journal=journal,
                raw={
                    "hal_id": hal_id,
                    "doc_type": doc_type,
                    "external_links": ext_links,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 HAL doc 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        rows: int = 10,
    ) -> SearchResponse:
        """使用 Solr 查询语法搜索 HAL。

        Args:
            query: Solr 查询串，可使用字段限定（如 ``title_t:neural``）
                   或自然关键词（默认全文检索）。
            rows: 返回结果数量。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "q": query,
            "fl": _FIELDS,
            "rows": rows,
            "wt": "json",
            "sort": "score desc",
        }

        resp = await self._client.get("/search/", params=params)
        data: dict[str, Any] = resp.json()

        response_block = data.get("response") or {}
        docs = response_block.get("docs") or []
        total = response_block.get("numFound", len(docs))

        results: list[PaperResult] = []
        for doc in docs:
            try:
                results.append(self._parse_doc(doc))
            except ParseError as exc:
                logger.debug("跳过解析失败的 HAL doc: %s", exc)

        return SearchResponse(
            query=query,
            total_results=total,
            page=1,
            per_page=rows,
            results=results,
            source=SourceType.HAL,
        )
