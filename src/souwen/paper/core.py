"""CORE API 客户端

官方文档: https://core.ac.uk/documentation/api
鉴权: 需免费 API Key (Bearer Token)
注册: https://core.ac.uk/services/api

文件用途：CORE 开放获取文献搜索客户端，聚合全球开放获取论文全文。

函数/类清单：
    CoreClient（类）
        - 功能：CORE 开放获取搜索客户端，管理 API 连接、限流和数据解析。
        - 关键属性：api_key (str) API 密钥, _client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 令牌桶限流器（~10 req/s）

    _parse_work(work: dict) -> PaperResult
        - 功能：将 CORE API 返回的 work JSON 对象转换为统一的 PaperResult 数据模型
        - 输入：work CORE API 返回的单条文献 JSON 对象
        - 输出：统一的 PaperResult 模型，包含标题、作者、DOI、全文链接等字段
        - 关键变量：authors (list[Author]) 作者列表, doi (str|None) DOI 标识符

    search(query: str, limit: int = 10, offset: int = 0) -> SearchResponse
        - 功能：按关键词搜索 CORE 文献库
        - 输入：query 检索关键词, limit 返回条数（最大 100）, offset 分页偏移量
        - 输出：SearchResponse 包含搜索结果列表、总数、分页信息
        - 限流：通过 _limiter.acquire() 控制请求频率

    get_work(core_id: str) -> PaperResult
        - 功能：通过 CORE 文献 ID 获取单条文献详情
        - 输入：core_id CORE 文献唯一标识符
        - 输出：PaperResult 模型
        - 异常：NotFoundError 文献不存在时抛出

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - PaperResult, SourceType: 统一的论文数据模型
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.core.ac.uk/v3"
_REGISTER_URL = "https://core.ac.uk/services/api"

# CORE 免费 Key 限流: ~10 req/s
_DEFAULT_RPS = 10.0


class CoreClient:
    """CORE 开放获取文献搜索客户端。

    CORE 聚合全球开放获取论文全文，适合获取免费全文 PDF。

    Raises:
        ConfigError: 未配置 core_api_key 时抛出。
    """

    def __init__(self, api_key: str | None = None) -> None:
        """初始化 CORE 客户端。

        Args:
            api_key: CORE API Key。未提供时从全局配置读取。

        Raises:
            ConfigError: API Key 未配置。
        """
        cfg = get_config()
        self.api_key: str = api_key or cfg.resolve_api_key("core", "core_api_key") or ""

        if not self.api_key:
            raise ConfigError(
                key="core_api_key",
                service="CORE",
                register_url=_REGISTER_URL,
            )

        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
        }

        self._client = SouWenHttpClient(base_url=_BASE_URL, headers=headers, source_name="core")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> CoreClient:
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
    def _parse_work(work: dict[str, Any]) -> PaperResult:
        """将 CORE work 对象转换为 PaperResult。

        Args:
            work: CORE API 返回的单条文献 JSON。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            # 提取作者列表：authors 可能是字典或列表形式
            raw_authors = work.get("authors", [])
            authors: list[Author] = []
            for a in raw_authors:
                name = a.get("name", "") if isinstance(a, dict) else str(a)
                if name:
                    authors.append(Author(name=name))

            # 提取 DOI：优先在 identifiers 数组中寻找，再检查顶层 doi 字段
            doi: str | None = None
            for identifier in work.get("identifiers", []):
                if isinstance(identifier, str) and identifier.startswith("10."):
                    doi = identifier
                    break

            # 如未在 identifiers 中找到，检查顶层 doi 字段
            if not doi:
                doi = work.get("doi")

            # 提取出版年份
            year: int | None = work.get("yearPublished")

            # 全文 PDF 下载链接
            download_url: str | None = work.get("downloadUrl")

            # 提取语言信息（可能为嵌套字典或字符串）
            language: str | None = (
                work.get("language", {}).get("code")
                if isinstance(work.get("language"), dict)
                else work.get("language")
            )

            # 提取期刊名称（journals 是列表）
            journals = work.get("journals") or []
            journal_name: str | None = (
                journals[0].get("title") if journals and isinstance(journals[0], dict) else None
            )

            return PaperResult(
                title=work.get("title", ""),
                authors=authors,
                abstract=work.get("abstract", ""),
                doi=doi,
                year=year,
                publication_date=work.get("publishedDate"),
                source=SourceType.CORE,
                source_url=(work.get("sourceFulltextUrls") or [""])[0]
                or f"https://core.ac.uk/works/{work.get('id', '')}"
                if work.get("sourceFulltextUrls")
                else None,
                pdf_url=download_url,
                citation_count=work.get("citationCount"),
                journal=journal_name,
                raw={
                    "language": language,
                    "publisher": work.get("publisher"),
                    "journals": work.get("journals"),
                    "fulltext_available": work.get("fullText") is not None,
                    "data_provider": work.get("dataProvider", {}).get("name")
                    if isinstance(work.get("dataProvider"), dict)
                    else None,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 CORE work 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
    ) -> SearchResponse:
        """搜索 CORE 文献。

        Args:
            query: 检索关键词。
            limit: 返回条数。
            offset: 偏移量。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "q": query,
            "limit": min(limit, 100),
            "offset": offset,
        }

        resp = await self._client.get("/search/works", params=params)
        data: dict[str, Any] = resp.json()

        results_list = data.get("results", [])
        results = [self._parse_work(w) for w in results_list]

        return SearchResponse(
            query=query,
            total_results=data.get("totalHits", len(results)),
            page=(offset // limit) + 1 if limit else 1,
            per_page=limit,
            results=results,
            source=SourceType.CORE,
        )

    async def get_work(self, core_id: str) -> PaperResult:
        """通过 CORE ID 获取文献详情。

        Args:
            core_id: CORE 文献 ID。

        Returns:
            PaperResult 模型。

        Raises:
            NotFoundError: 文献不存在。
        """
        await self._limiter.acquire()

        resp = await self._client.get(f"/works/{core_id}")

        if resp.status_code == 404:
            raise NotFoundError(f"CORE 未找到文献 ID: {core_id}")

        return self._parse_work(resp.json())
