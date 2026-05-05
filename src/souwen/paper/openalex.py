"""OpenAlex API 客户端

官方文档: https://docs.openalex.org/
鉴权: 无需 Key，请求头加 mailto 进入 polite pool
限流: polite pool 内无硬限制，建议 ~10 req/s

文件用途：OpenAlex 论文搜索客户端，提供完整的开放获取论文元数据和 OA 状态。

函数/类清单：
    OpenAlexClient（类）
        - 功能：OpenAlex 论文搜索和查询客户端，支持关键词/DOI/ID 多种检索方式
        - 关键属性：mailto (str|None) 联系邮箱, _client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（~10 req/s）

    _common_params() -> dict
        - 功能：构建所有 API 请求的公共参数（如 mailto）
        - 输出：请求参数字典

    _reconstruct_abstract(inverted_index: dict|None) -> str
        - 功能：从 OpenAlex 的倒排索引格式重建完整摘要文本
        - 输入：inverted_index OpenAlex 返回的 abstract_inverted_index
        - 输出：还原后的摘要纯文本
        - 说明：OpenAlex 使用 {word: [positions]} 格式存储摘要以节省空间

    _parse_work(work: dict) -> PaperResult
        - 功能：将 OpenAlex Work 对象转换为 PaperResult
        - 输入：work OpenAlex API 返回的单条 work JSON
        - 输出：统一的 PaperResult 模型，包含 OA 状态和最佳 OA 位置

    search(query: str, filters: dict|None, sort: str|None, page: int, per_page: int)
           -> SearchResponse
        - 功能：全文搜索论文
        - 输入：query 检索关键词, filters 过滤条件, sort 排序, page 页码, per_page 每页条数
        - 输出：SearchResponse 包含结果列表及分页信息

    get_by_doi(doi: str) -> PaperResult
        - 功能：通过 DOI 获取论文详情
        - 输入：doi 论文 DOI

    get_by_id(openalex_id: str) -> PaperResult
        - 功能：通过 OpenAlex ID 获取论文详情
        - 输入：openalex_id OpenAlex 标识（如 W2741809807 或完整 URL）

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - safe_parse_date: 安全日期解析工具
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.core.parsing import safe_parse_date
from souwen.config import get_config
from souwen.core.exceptions import NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openalex.org"

# polite pool 推荐速率
_DEFAULT_RPS = 10.0


class OpenAlexClient:
    """OpenAlex 论文搜索客户端。

    Attributes:
        mailto: 用于进入 polite pool 的邮箱地址，可选。
    """

    def __init__(self, mailto: str | None = None) -> None:
        """初始化 OpenAlex 客户端。

        Args:
            mailto: 联系邮箱。未提供时从全局配置读取。
        """
        cfg = get_config()
        self.mailto: str | None = mailto or cfg.resolve_api_key("openalex", "openalex_email")
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="openalex")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> OpenAlexClient:
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

    def _common_params(self) -> dict[str, str]:
        """构建公共请求参数。

        如果配置了 mailto，将其加入参数以进入 polite pool（提升限流阈值）。
        """
        params: dict[str, str] = {}
        if self.mailto:
            params["mailto"] = self.mailto
        return params

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
        """从倒排索引重建摘要文本。

        OpenAlex 以 ``{word: [positions]}`` 的形式存储摘要，
        需要按位置还原为连续文本。

        Args:
            inverted_index: OpenAlex 返回的 abstract_inverted_index。

        Returns:
            还原后的摘要纯文本；若输入为空则返回空字符串。
        """
        if not inverted_index:
            return ""
        # 展开为 (position, word) 元组列表
        position_word: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                position_word.append((pos, word))
        # 按位置排序
        position_word.sort(key=lambda x: x[0])
        # 拼接为连续文本
        return " ".join(w for _, w in position_word)

    def _parse_work(self, work: dict[str, Any]) -> PaperResult:
        """将 OpenAlex Work 对象转换为 PaperResult。

        Args:
            work: OpenAlex API 返回的单条 work JSON。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 关键字段缺失或格式异常。
        """
        try:
            # 提取作者列表及其所属机构
            authors: list[Author] = []
            for authorship in work.get("authorships", []):
                author_obj = authorship.get("author", {})
                # 提取该作者的所有机构名称并用分号连接
                authors.append(
                    Author(
                        name=author_obj.get("display_name", ""),
                        affiliation="; ".join(
                            inst.get("display_name", "")
                            for inst in authorship.get("institutions", [])
                            if inst.get("display_name")
                        )
                        or None,
                    )
                )

            # 提取 DOI 并去除 URL 前缀（OpenAlex 返回完整 DOI URL）
            raw_doi: str | None = work.get("doi")
            doi: str | None = None
            if raw_doi:
                # 去除常见的 DOI URL 前缀，提取纯 DOI
                doi = raw_doi.replace("https://doi.org/", "").replace("http://doi.org/", "")

            # 从倒排索引重建摘要
            abstract = self._reconstruct_abstract(work.get("abstract_inverted_index"))

            # 提取出版年份和日期
            pub_year: int | None = work.get("publication_year")
            pub_date = safe_parse_date(work.get("publication_date"))

            # 提取最佳 OA PDF 链接（OpenAlex 会自动选择最佳 OA 来源）
            best_oa = work.get("best_oa_location") or {}
            pdf_url: str | None = best_oa.get("pdf_url")

            # 提取发表期刊/会议名称
            primary_loc = work.get("primary_location") or {}
            source_info = primary_loc.get("source") or {}
            journal_name: str | None = source_info.get("display_name") or None

            return PaperResult(
                title=work.get("display_name", work.get("title", "")),
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=pub_year,
                publication_date=pub_date,
                source=SourceType.OPENALEX,
                source_url=work.get("id", ""),
                pdf_url=pdf_url,
                citation_count=work.get("cited_by_count"),
                journal=journal_name,
                raw={
                    "type": work.get("type"),
                    "is_oa": work.get("open_access", {}).get("is_oa"),
                    # 取前 5 个主要研究概念
                    "concepts": [c.get("display_name") for c in work.get("concepts", [])[:5]],
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 OpenAlex work 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        filters: dict[str, str] | None = None,
        sort: str | None = None,
        page: int = 1,
        per_page: int = 10,
    ) -> SearchResponse:
        """全文搜索论文。

        Args:
            query: 检索关键词。
            filters: OpenAlex filter 参数，如 ``{"from_publication_date": "2023-01-01"}``。
            sort: 排序字段，如 ``"cited_by_count:desc"``。
            page: 页码（从 1 开始）。
            per_page: 每页条数，上限 200。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params = self._common_params()
        params["search"] = query
        params["page"] = str(page)
        params["per_page"] = str(min(per_page, 200))

        if filters:
            filter_parts = [f"{k}:{v}" for k, v in filters.items()]
            params["filter"] = ",".join(filter_parts)
        if sort:
            params["sort"] = sort

        resp = await self._client.get("/works", params=params)
        data: dict[str, Any] = resp.json()

        results = [self._parse_work(w) for w in data.get("results", [])]
        meta = data.get("meta", {})

        return SearchResponse(
            query=query,
            total_results=meta.get("count", len(results)),
            page=page,
            per_page=per_page,
            results=results,
            source=SourceType.OPENALEX,
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
        params = self._common_params()

        resp = await self._client.get(f"/works/https://doi.org/{doi}", params=params)
        if resp.status_code == 404:
            raise NotFoundError(f"OpenAlex 未找到 DOI: {doi}")

        return self._parse_work(resp.json())

    async def get_by_id(self, openalex_id: str) -> PaperResult:
        """通过 OpenAlex ID 获取论文详情。

        Args:
            openalex_id: OpenAlex 标识，如 ``"W2741809807"`` 或完整 URL。

        Returns:
            PaperResult 模型。

        Raises:
            NotFoundError: ID 不存在。
        """
        await self._limiter.acquire()
        params = self._common_params()

        # 支持短 ID 或完整 URL
        if openalex_id.startswith("http"):
            url = openalex_id
        else:
            url = f"/works/{openalex_id}"

        resp = await self._client.get(url, params=params)
        if resp.status_code == 404:
            raise NotFoundError(f"OpenAlex 未找到 ID: {openalex_id}")

        return self._parse_work(resp.json())
