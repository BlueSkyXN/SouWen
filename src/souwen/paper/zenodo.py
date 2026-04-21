"""Zenodo REST API 客户端

官方文档: https://developers.zenodo.org/
鉴权: 无需 Key（基础搜索），可选 Access Token 以提升限流
限流: 匿名约 60 req/min，有 Token 更高
返回: JSON

文件用途：Zenodo 开放科研仓储搜索客户端，覆盖论文、数据集、软件、
演示文稿等多种科研产出类型。

函数/类清单：
    ZenodoClient（类）
        - 功能：Zenodo REST API 搜索客户端，支持全文关键词搜索
        - 关键属性：access_token (str|None) Zenodo Access Token（可选），
                   _client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（1 req/s）

    _parse_record(record: dict) -> PaperResult
        - 功能：将 Zenodo record JSON 对象转换为 PaperResult
        - 输入：record hits.hits 数组中的单条记录
        - 输出：统一的 PaperResult 模型，包含 DOI、作者、文件链接等

    search(query: str, size: int, page: int, record_type: str) -> SearchResponse
        - 功能：关键词搜索 Zenodo 记录
        - 输入：query 检索词，size 每页条数（最大 1000），page 页码，
               record_type 记录类型（默认 "publication"，可为 "" 搜索全部）
        - 输出：SearchResponse 包含结果列表及分页信息

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://zenodo.org/api"

# 匿名约 60 req/min，保守取 1 req/s
_RATE_LIMIT_RPS = 1.0


class ZenodoClient:
    """Zenodo 开放科研仓储搜索客户端。

    无需 API Key 即可使用基础搜索功能。
    提供 access_token 可解锁更高限流并访问私有记录。
    """

    def __init__(self, access_token: str | None = None) -> None:
        """初始化 Zenodo 客户端。

        Args:
            access_token: Zenodo Access Token（可选）。未提供时从全局配置读取。
        """
        cfg = get_config()
        self.access_token: str | None = (
            access_token or cfg.resolve_api_key("zenodo", "zenodo_access_token")
        )
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="zenodo")
        self._limiter = TokenBucketLimiter(rate=_RATE_LIMIT_RPS, burst=2.0)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> ZenodoClient:
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
    def _parse_record(record: dict[str, Any]) -> PaperResult:
        """将 Zenodo record JSON 对象转换为 PaperResult。

        Args:
            record: Zenodo hits.hits 数组中的单条记录 JSON。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            meta: dict[str, Any] = record.get("metadata", {})

            title = (meta.get("title") or "").strip()
            doi = meta.get("doi") or record.get("doi") or None
            description = (meta.get("description") or "").strip() or None

            # 作者列表（creators 数组，每项含 name 和可选的 affiliation）
            authors: list[Author] = []
            for creator in meta.get("creators", []):
                name = (creator.get("name") or "").strip()
                affiliation = (creator.get("affiliation") or "").strip() or None
                orcid = creator.get("orcid") or None
                if name:
                    authors.append(Author(name=name, affiliation=affiliation, orcid=orcid))

            # 发表日期（publication_date 格式 YYYY-MM-DD 或 YYYY）
            pub_date_raw = meta.get("publication_date") or ""
            year: int | None = None
            pub_date: str | None = None
            if pub_date_raw:
                pub_date = pub_date_raw if len(pub_date_raw) >= 10 else f"{pub_date_raw}-01-01"
                try:
                    year = int(pub_date_raw[:4])
                except (ValueError, IndexError):
                    pass

            # 期刊/场地信息（部分记录有 journal 字段）
            journal_info = meta.get("journal") or {}
            journal_title = journal_info.get("title") or None

            # 构建记录 URL
            record_id = record.get("id") or record.get("record_id") or ""
            links = record.get("links", {})
            source_url = links.get("html") or links.get("self") or (
                f"https://zenodo.org/records/{record_id}" if record_id else ""
            )

            # 查找 PDF 文件链接（files 数组中 key 含 .pdf 的项）
            pdf_url: str | None = None
            for f in record.get("files", []):
                key = f.get("key", "")
                if key.lower().endswith(".pdf"):
                    file_links = f.get("links", {})
                    pdf_url = file_links.get("self") or None
                    break

            # 被引次数（部分记录提供 stats.citations）
            citation_count: int | None = None
            stats = record.get("stats", {})
            if stats.get("citations"):
                try:
                    citation_count = int(stats["citations"])
                except (ValueError, TypeError):
                    pass

            return PaperResult(
                title=title,
                authors=authors,
                abstract=description,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=SourceType.ZENODO,
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=citation_count,
                journal=journal_title,
                raw={
                    "record_id": str(record_id),
                    "resource_type": meta.get("resource_type", {}).get("type"),
                    "access_right": meta.get("access_right"),
                    "license": meta.get("license", {}).get("id"),
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 Zenodo 记录失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        size: int = 10,
        page: int = 1,
        record_type: str = "publication",
    ) -> SearchResponse:
        """关键词搜索 Zenodo 记录。

        Args:
            query: 检索词，支持 Elasticsearch 查询语法。
            size: 每页条数，最大 1000。
            page: 页码，从 1 开始。
            record_type: 记录类型过滤，如 ``"publication"``、``"dataset"``、
                         ``"software"``，或 ``""`` 搜索全部类型。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, Any] = {
            "q": query,
            "size": min(size, 1000),
            "page": page,
        }
        if record_type:
            params["type"] = record_type
        if self.access_token:
            params["access_token"] = self.access_token

        resp = await self._client.get("/records", params=params)
        try:
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            raise ParseError(f"Zenodo JSON 解析失败: {exc}") from exc

        hits = data.get("hits", {})
        total: int = 0
        try:
            total = int(hits.get("total", 0))
        except (ValueError, TypeError):
            pass

        records: list[dict[str, Any]] = hits.get("hits", [])
        results: list[PaperResult] = []
        for record in records:
            try:
                results.append(self._parse_record(record))
            except ParseError as exc:
                logger.warning("跳过解析失败的 Zenodo 记录: %s", exc)

        return SearchResponse(
            query=query,
            total_results=total or len(results),
            page=page,
            per_page=size,
            results=results,
            source=SourceType.ZENODO,
        )
