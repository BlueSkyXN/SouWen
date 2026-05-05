"""Crossref API 客户端

官方文档: https://api.crossref.org/swagger-ui/index.html
鉴权: 无需 Key，mailto 进入 polite pool
核心价值: 权威 DOI 元数据

文件用途：Crossref 论文元数据客户端，提供权威的 DOI 元数据查询服务。

函数/类清单：
    CrossrefClient（类）
        - 功能：Crossref 论文元数据搜索和查询客户端
        - 关键属性：mailto (str|None) 联系邮箱（进入 polite pool 可提升限流阈值），
                   _client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（~10 req/s）

    _extract_publication_date(item: dict) -> tuple[int|None, str|None, str|None, str|None]
        - 功能：从 Crossref work 项目中提取日期信息，支持多种日期格式
        - 输入：item Crossref API 返回的 work JSON 对象
        - 输出：(year, publication_date, raw_pub_date, date_precision) 元组
        - 关键变量：date_parts (list) 日期分部（年月日）, precision (str) 精度级别

    _parse_item(item: dict) -> PaperResult
        - 功能：将 Crossref work item JSON 转换为 PaperResult 数据模型
        - 输入：item Crossref API 返回的单条 work JSON
        - 输出：统一的 PaperResult 模型，包含标题、作者、DOI、引用数等
        - 异常：ParseError 关键字段缺失或格式异常时抛出

    search(query: str, filters: dict|None, sort: str|None, rows: int, offset: int)
           -> SearchResponse
        - 功能：全文搜索 Crossref 论文库
        - 输入：query 检索关键词, filters 过滤条件（如 from-pub-date），
               sort 排序字段, rows 返回条数（最多 1000）, offset 分页偏移
        - 输出：SearchResponse 包含结果列表及分页信息

    get_by_doi(doi: str) -> PaperResult
        - 功能：通过 DOI 获取论文详情
        - 输入：doi 论文 DOI（如 "10.1038/s41586-021-03819-2"）
        - 输出：PaperResult 模型
        - 异常：NotFoundError 当 DOI 不存在时抛出

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.crossref.org"

# polite pool 推荐速率
_DEFAULT_RPS = 10.0


class CrossrefClient:
    """Crossref 论文元数据客户端。

    Attributes:
        mailto: 用于进入 polite pool 的邮箱地址。
    """

    def __init__(self, mailto: str | None = None) -> None:
        """初始化 Crossref 客户端。

        Args:
            mailto: 联系邮箱。未提供时从全局配置读取。
        """
        cfg = get_config()
        self.mailto: str | None = mailto or cfg.resolve_api_key("crossref", "crossref_mailto")

        headers: dict[str, str] = {
            "User-Agent": f"SouWen/1.0 (mailto:{self.mailto})" if self.mailto else "SouWen/1.0",
        }

        self._client = SouWenHttpClient(base_url=_BASE_URL, headers=headers, source_name="crossref")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> CrossrefClient:
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
    def _extract_publication_date(
        item: dict[str, Any],
    ) -> tuple[int | None, str | None, str | None, str | None]:
        """提取日期信息；支持多种日期格式，返回规范化的日期及精度级别。

        Crossref 的日期信息存在多个层级（published-print/published-online/created），
        按优先级依次尝试提取。
        """
        # 按优先级尝试不同的日期来源
        date_parts = (
            item.get("published-print", {}).get("date-parts")
            or item.get("published-online", {}).get("date-parts")
            or item.get("created", {}).get("date-parts")
        )
        if not date_parts or not date_parts[0]:
            return None, None, None, None

        # 规范化日期部分为整数列表（年/月/日），最多取前 3 个元素
        normalized: list[int] = []
        for part in date_parts[0][:3]:
            try:
                normalized.append(int(part))
            except (TypeError, ValueError):
                # 若无法转换为整数，停止处理后续部分
                break

        if not normalized:
            return None, None, None, None

        # 构建不同精度的日期字符串
        year = normalized[0]
        raw_date = f"{year:04d}"
        if len(normalized) >= 2:
            raw_date += f"-{normalized[1]:02d}"
        if len(normalized) >= 3:
            raw_date += f"-{normalized[2]:02d}"

        # 日期精度：year/month/day
        precision = {1: "year", 2: "month", 3: "day"}.get(len(normalized))
        # 仅当日期精度为 day 时，才作为 publication_date；其他情况为 None
        publication_date = raw_date if len(normalized) >= 3 else None
        return year, publication_date, raw_date, precision

    @staticmethod
    def _parse_item(item: dict[str, Any]) -> PaperResult:
        """将 Crossref work item 转换为 PaperResult。

        Args:
            item: Crossref API 返回的单条 work JSON。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 关键字段缺失或格式异常。
        """
        try:
            # 提取标题（Crossref 返回标题为列表）
            titles: list[str] = item.get("title", [])
            title = titles[0] if titles else ""

            # 提取作者列表及其机构信息
            authors: list[Author] = []
            for a in item.get("author", []):
                # 作者名称由 given（名）和 family（姓）组成
                name_parts = [a.get("given", ""), a.get("family", "")]
                full_name = " ".join(p for p in name_parts if p).strip()
                # 提取所有关联机构
                affiliations = [
                    aff.get("name", "") for aff in a.get("affiliation", []) if aff.get("name")
                ]
                if full_name:
                    authors.append(
                        Author(
                            name=full_name,
                            affiliation="; ".join(affiliations) if affiliations else None,
                        )
                    )

            # 提取摘要（部分记录可能含 JATS XML 标签，需清理）
            abstract_raw: str = item.get("abstract", "")
            # 简单去除常见的 JATS 标签
            abstract = abstract_raw
            for tag in ("<jats:p>", "</jats:p>", "<jats:title>", "</jats:title>"):
                abstract = abstract.replace(tag, "")
            abstract = abstract.strip()

            # 提取发表日期及年份
            year, pub_date, raw_pub_date, date_precision = CrossrefClient._extract_publication_date(
                item
            )

            # 提取 DOI
            doi: str | None = item.get("DOI")

            # 提取 PDF 下载链接
            links = item.get("link", [])
            pdf_url: str | None = None
            for link in links:
                if link.get("content-type") == "application/pdf":
                    pdf_url = link.get("URL")
                    break

            # 提取期刊名称（container-title 是列表）
            container_title = (item.get("container-title") or [None])[0]

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=SourceType.CROSSREF,
                source_url=f"https://doi.org/{doi}" if doi else "",
                pdf_url=pdf_url,
                citation_count=item.get("is-referenced-by-count"),
                journal=container_title,
                raw={
                    "type": item.get("type"),
                    "container_title": (item.get("container-title") or [None])[0],
                    "issn": item.get("ISSN"),
                    "publisher": item.get("publisher"),
                    "subject": item.get("subject"),
                    "publication_date_raw": raw_pub_date,
                    "publication_date_precision": date_precision,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 Crossref item 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        filters: dict[str, str] | None = None,
        sort: str | None = None,
        rows: int = 10,
        offset: int = 0,
    ) -> SearchResponse:
        """全文搜索论文。

        Args:
            query: 检索关键词。
            filters: Crossref filter 参数，如 ``{"from-pub-date": "2023"}``。
            sort: 排序字段，如 ``"relevance"``、``"published"``。
            rows: 返回条数，上限 1000。
            offset: 偏移量。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "query": query,
            "rows": min(rows, 1000),
            "offset": offset,
        }
        if self.mailto:
            params["mailto"] = self.mailto
        if filters:
            filter_parts = [f"{k}:{v}" for k, v in filters.items()]
            params["filter"] = ",".join(filter_parts)
        if sort:
            params["sort"] = sort

        resp = await self._client.get("/works", params=params)
        data: dict[str, Any] = resp.json()
        message = data.get("message", {})

        results: list[PaperResult] = []
        for item in message.get("items", []):
            try:
                results.append(self._parse_item(item))
            except ParseError as exc:
                logger.warning(
                    "Crossref item parse failure: %s (doi=%s, title=%s)",
                    exc,
                    item.get("DOI"),
                    (item.get("title") or [None])[0],
                )

        return SearchResponse(
            query=query,
            total_results=message.get("total-results", len(results)),
            page=(offset // rows) + 1 if rows else 1,
            per_page=rows,
            results=results,
            source=SourceType.CROSSREF,
        )

    async def get_by_doi(self, doi: str) -> PaperResult:
        """通过 DOI 获取论文详情。

        Args:
            doi: 论文 DOI，例如 ``"10.1038/s41586-021-03819-2"``。

        Returns:
            PaperResult 模型。

        Raises:
            NotFoundError: DOI 不存在。
        """
        await self._limiter.acquire()

        params: dict[str, str] = {}
        if self.mailto:
            params["mailto"] = self.mailto

        resp = await self._client.get(f"/works/{doi}", params=params)

        if resp.status_code == 404:
            raise NotFoundError(f"Crossref 未找到 DOI: {doi}")

        data: dict[str, Any] = resp.json()
        return self._parse_item(data.get("message", {}))
