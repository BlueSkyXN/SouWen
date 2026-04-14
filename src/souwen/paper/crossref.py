"""Crossref API 客户端

官方文档: https://api.crossref.org/swagger-ui/index.html
鉴权: 无需 Key，mailto 进入 polite pool
核心价值: 权威 DOI 元数据
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import NotFoundError, ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

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
        """提取日期信息；部分日期保留原始值但不强制映射为完整 date。"""
        date_parts = (
            item.get("published-print", {}).get("date-parts")
            or item.get("published-online", {}).get("date-parts")
            or item.get("created", {}).get("date-parts")
        )
        if not date_parts or not date_parts[0]:
            return None, None, None, None

        normalized: list[int] = []
        for part in date_parts[0][:3]:
            try:
                normalized.append(int(part))
            except (TypeError, ValueError):
                break

        if not normalized:
            return None, None, None, None

        year = normalized[0]
        raw_date = f"{year:04d}"
        if len(normalized) >= 2:
            raw_date += f"-{normalized[1]:02d}"
        if len(normalized) >= 3:
            raw_date += f"-{normalized[2]:02d}"

        precision = {1: "year", 2: "month", 3: "day"}.get(len(normalized))
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
            # 标题可能是列表
            titles: list[str] = item.get("title", [])
            title = titles[0] if titles else ""

            # 作者
            authors: list[Author] = []
            for a in item.get("author", []):
                name_parts = [a.get("given", ""), a.get("family", "")]
                full_name = " ".join(p for p in name_parts if p).strip()
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

            # 摘要（部分记录含 HTML 标签，做基础清理）
            abstract_raw: str = item.get("abstract", "")
            # 简单去除 jats 标签
            abstract = abstract_raw
            for tag in ("<jats:p>", "</jats:p>", "<jats:title>", "</jats:title>"):
                abstract = abstract.replace(tag, "")
            abstract = abstract.strip()

            # 发表日期
            year, pub_date, raw_pub_date, date_precision = CrossrefClient._extract_publication_date(
                item
            )

            # DOI
            doi: str | None = item.get("DOI")

            # 链接
            links = item.get("link", [])
            pdf_url: str | None = None
            for link in links:
                if link.get("content-type") == "application/pdf":
                    pdf_url = link.get("URL")
                    break

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
