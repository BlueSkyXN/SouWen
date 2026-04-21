"""Zenodo API 客户端

官方文档: https://developers.zenodo.org/
鉴权: 可选 Personal Access Token (Authorization: Bearer ...)
注册: https://zenodo.org/account/settings/applications/tokens/new/

文件用途：Zenodo（CERN 开放科学仓库）出版物搜索客户端，覆盖 preprint、
期刊文章、技术报告等开放获取的科研出版物，并附带可下载文件链接。

函数/类清单：
    ZenodoClient（类）
        - 功能：Zenodo records API 搜索客户端，仅检索 type=publication 类资源
        - 关键属性：access_token (str|None) 可选个人访问令牌,
                   _client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 令牌桶限流器（5 req/s）

    _strip_html(text: str) -> str
        - 功能：剥离描述字段中的 HTML 标签
        - 输入：可能含 HTML 标签的字符串
        - 输出：纯文本字符串

    _parse_record(record: dict) -> PaperResult
        - 功能：将 Zenodo record 对象转换为统一的 PaperResult 数据模型
        - 输入：Zenodo API 单条记录（含 metadata、files、links）
        - 输出：PaperResult，pdf_url 取首个 .pdf 文件的下载链接

    search(query: str, size: int = 10) -> SearchResponse
        - 功能：按关键词搜索 Zenodo 出版物（按最新发布排序）
        - 输入：query 检索关键词, size 返回条数
        - 输出：SearchResponse 包含结果列表及总数

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - PaperResult, SearchResponse: 统一论文数据模型
"""

from __future__ import annotations

import logging
import re
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://zenodo.org/api"
_RECORDS_URL = "https://zenodo.org/records"

# Zenodo 限流：保守 5 req/s
_DEFAULT_RPS = 5.0

_HTML_TAG_RE = re.compile(r"<[^>]+>")


class ZenodoClient:
    """Zenodo 开放科学仓库出版物搜索客户端。

    特点:
        - CERN 维护的开放科学仓库，覆盖 preprint、期刊文章、报告等
        - 默认仅检索出版物（type=publication），过滤数据集/软件/海报
        - 提供文件下载链接，可直接获取 PDF
        - 不提供引用计数
        - Access Token 可选，匿名访问也可用
    """

    def __init__(self, access_token: str | None = None) -> None:
        """初始化 Zenodo 客户端。

        Args:
            access_token: Zenodo Personal Access Token（可选）。未提供时
                          从全局配置读取，仍未配置则匿名访问。
        """
        cfg = get_config()
        self.access_token: str | None = (
            access_token or cfg.resolve_api_key("zenodo", "zenodo_access_token")
        )

        headers: dict[str, str] = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        self._client = SouWenHttpClient(
            base_url=_BASE_URL,
            headers=headers,
            source_name="zenodo",
        )
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

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
    def _strip_html(text: str) -> str:
        """剥离字符串中的 HTML 标签。

        Zenodo description 字段常含 <p>、<br>、<a> 等 HTML 标签，
        此处简单去除以获得纯文本摘要。

        Args:
            text: 可能含 HTML 标签的字符串。

        Returns:
            去除标签后的文本。
        """
        if not text:
            return ""
        return _HTML_TAG_RE.sub("", text).strip()

    @staticmethod
    def _parse_record(record: dict[str, Any]) -> PaperResult:
        """将 Zenodo record 转换为 PaperResult。

        Zenodo 响应结构：
        {
            "id": 12345,
            "metadata": {
                "title": "...",
                "creators": [{"name": "Doe, John"}, ...],
                "description": "<p>HTML abstract</p>",
                "publication_date": "2024-01-15",
                "doi": "10.5281/zenodo.12345",
                "keywords": [...],
                "license": {"id": "..."},
                "resource_type": {"type": "publication", "subtype": "article"}
            },
            "files": [{"key": "paper.pdf", "links": {"self": "..."}}],
            "links": {"html": "https://zenodo.org/records/12345"}
        }

        Args:
            record: Zenodo API 单条 record 对象。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            metadata: dict[str, Any] = record.get("metadata", {}) or {}
            record_id = record.get("id", "")
            links: dict[str, Any] = record.get("links", {}) or {}

            title: str = metadata.get("title", "") or ""

            # 作者：creators[].name 通常为 "Last, First"，原样保留
            authors: list[Author] = []
            for creator in metadata.get("creators", []) or []:
                name = (
                    creator.get("name", "")
                    if isinstance(creator, dict)
                    else str(creator)
                )
                if name:
                    authors.append(Author(name=name))

            # 摘要：去除 HTML 标签
            abstract = ZenodoClient._strip_html(metadata.get("description", "") or "") or None

            # DOI
            doi: str | None = metadata.get("doi") or None

            # 出版日期：YYYY-MM-DD
            pub_date: str | None = metadata.get("publication_date") or None
            year: int | None = None
            if pub_date and len(pub_date) >= 4:
                try:
                    year = int(pub_date[:4])
                except ValueError:
                    year = None

            # 文件：找首个 .pdf 文件
            pdf_url: str | None = None
            for f in record.get("files", []) or []:
                if not isinstance(f, dict):
                    continue
                key = (f.get("key") or "").lower()
                if not key.endswith(".pdf"):
                    continue
                file_links = f.get("links", {}) or {}
                pdf_url = file_links.get("self") or file_links.get("download")
                if pdf_url:
                    break

            # 详情页 URL
            source_url: str = (
                links.get("html")
                or (f"{_RECORDS_URL}/{record_id}" if record_id else _RECORDS_URL)
            )

            # license / resource_type 提取
            license_obj = metadata.get("license") or {}
            license_id = (
                license_obj.get("id") if isinstance(license_obj, dict) else license_obj
            )
            resource_type = metadata.get("resource_type") or {}
            resource_subtype = (
                resource_type.get("subtype") if isinstance(resource_type, dict) else None
            )

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source="zenodo",  # type: ignore[arg-type]
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,  # Zenodo 不提供引用数
                raw={
                    "zenodo_id": record_id,
                    "keywords": metadata.get("keywords") or [],
                    "access_right": metadata.get("access_right"),
                    "license": license_id,
                    "resource_subtype": resource_subtype,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 Zenodo record 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        size: int = 10,
    ) -> SearchResponse:
        """搜索 Zenodo 出版物。

        默认追加 type=publication 过滤，仅返回出版物（排除数据集、
        软件、海报、视频等非论文资源）。结果按最新发布排序。

        Args:
            query: 检索关键词，支持 Elasticsearch 查询语法。
            size: 返回条数。

        Returns:
            SearchResponse 包含结果列表及总数。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "q": query,
            "size": size,
            "sort": "mostrecent",
            "type": "publication",  # 关键过滤：仅出版物
        }

        resp = await self._client.get("/records", params=params)
        data: dict[str, Any] = resp.json()

        hits_obj: dict[str, Any] = data.get("hits", {}) or {}
        records = hits_obj.get("hits", []) or []

        # total 在不同 API 版本下可能为 int 或 {"value": int}
        total_raw = hits_obj.get("total", len(records))
        if isinstance(total_raw, dict):
            total = int(total_raw.get("value", len(records)))
        else:
            try:
                total = int(total_raw)
            except (ValueError, TypeError):
                total = len(records)

        results: list[PaperResult] = []
        for record in records:
            try:
                results.append(self._parse_record(record))
            except ParseError as exc:
                logger.debug("跳过解析失败的 Zenodo record: %s", exc)

        return SearchResponse(
            query=query,
            total_results=total,
            page=1,
            per_page=size,
            results=results,
            source="zenodo",  # type: ignore[arg-type]
        )
