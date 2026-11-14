"""huggingface（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from souwen.common_runtime.provider_support.exceptions import ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.common_runtime.provider_support.rate_limiter import TokenBucketLimiter
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import RestJsonProviderSpec, RestJsonSearchProvider
from souwen.platform.provider_spec.models import (
    HttpOperation,
    SearchRequestMapping,
    SearchResponseMapping,
)
from souwen.providers.runtime_clients.models import Author, PaperResult, SearchResponse
from typing import Any, Protocol
from urllib.parse import quote


from souwen.platform.manifest_registry import ProviderManifest

HUGGINGFACE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "huggingface",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "huggingface-search",
                "capability": "search",
                "export": "HuggingFaceSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "huggingface-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["huggingface.co"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["huggingface-provider-config-v1"],
        },
    }
)


HUGGINGFACE_REST_SPEC = RestJsonProviderSpec(
    provider_id="huggingface",
    adapter_id="huggingface-search",
    host="huggingface.co",
    operation=HttpOperation(method="GET", endpoint="/api/papers/search"),
    request_mapping=SearchRequestMapping(query_field="query", limit_field="top_n"),
    response_mapping=SearchResponseMapping(
        source_field="source",
        items_field="results",
        total_field="total_results",
        page_field="page",
        limit_field="per_page",
        item_source_field="source",
        identifier_path="raw.arxiv_id",
        identifier_pattern=r"[A-Za-z0-9._-]+",
        identifier_scheme="arxiv",
        title_path="title",
        snippet_path="abstract",
        year_path="year",
        authors_path="authors",
        author_name_path="name",
        record_url_path="source_url",
        record_host="huggingface.co",
        record_path_template="/papers/{identifier}",
    ),
    configuration_keys=("enabled",),
)


logger = logging.getLogger(__name__)

_BASE_URL = "https://huggingface.co"

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
                source="huggingface",
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
            source="huggingface",
        )


class HuggingFaceClientProtocol(Protocol):
    async def search(self, query: str, top_n: int = 10) -> Any: ...
    async def close(self) -> None: ...


class HuggingFaceSearchProvider(RestJsonSearchProvider):
    def __init__(self, client: HuggingFaceClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, HUGGINGFACE_REST_SPEC, enabled=enabled)


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无通道覆盖
    return HuggingFaceSearchProvider(
        HuggingFaceClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = HUGGINGFACE_PROVIDER_MANIFEST
SPEC = HUGGINGFACE_REST_SPEC
PROVIDER_TYPE = HuggingFaceSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
