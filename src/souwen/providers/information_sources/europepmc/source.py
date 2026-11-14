"""europepmc（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence, Mapping
from souwen.common_runtime.provider_support.exceptions import ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.common_runtime.provider_support.rate_limiter import TokenBucketLimiter
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import (
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
    ClientSearchProvider,
    ClientSearchSpec,
)
from souwen.platform.provider_spec.models import HttpOperation
from souwen.platform.provider_spi import (
    PageInfo,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchIdentifier,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)
from souwen.providers.runtime_clients.models import Author, PaperResult, SearchResponse
from typing import Any, Protocol
from urllib.parse import urlsplit


from souwen.platform.manifest_registry import ProviderManifest

EUROPEPMC_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "europepmc",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "europepmc-search",
                "capability": "search",
                "export": "EuropePmcSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "europepmc-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["www.ebi.ac.uk"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["europepmc-provider-config-v1"],
        },
    }
)


EUROPEPMC_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="europepmc",
    adapter_id="europepmc-search",
    review_status="reviewed_adapter",
    adapter_reason="existing result URLs have reviewed PMC, MED, and source-specific branches",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="www.ebi.ac.uk",
        base_path="/europepmc/webservices/rest",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    configuration_keys=("enabled",),
)


logger = logging.getLogger(__name__)

_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

_DEFAULT_RPS = 5.0


class EuropePmcClient:
    """Europe PMC 生物医学开放获取文献搜索客户端。

    特点:
        - 聚合 PubMed/PMC/AGRICOLA 等多源，覆盖生命科学全领域
        - 提供 isOpenAccess、HAS_FT、fullTextUrlList 等开放获取信号
        - 返回 citedByCount，可用于影响力筛选
        - 无需 API Key，零配置即用
    """

    def __init__(self) -> None:
        """初始化 Europe PMC 客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="europepmc")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> EuropePmcClient:
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
        """将 Europe PMC 单条 result 转换为 PaperResult。

        Europe PMC search API 在 ``resultList.result[]`` 下返回每条记录，
        关键字段示例：
        {
            "id": "12345678",
            "source": "MED",                # MED=PubMed, PMC=PubMed Central, AGR=AGRICOLA
            "pmid": "12345678",
            "pmcid": "PMC1234567",
            "doi": "10.xxxx/yyyy",
            "title": "...",
            "authorList": {"author": [{"fullName": "Doe J"}, ...]},
            "abstractText": "...",
            "pubYear": "2024",
            "firstPublicationDate": "2024-01-15",
            "journalTitle": "...",
            "citedByCount": 42,
            "isOpenAccess": "Y",
            "fullTextUrlList": {"fullTextUrl": [
                {"documentStyle": "pdf", "url": "..."},
                {"documentStyle": "html", "url": "..."}
            ]},
            "keywordList": {"keyword": ["..."]}
        }

        Args:
            item: Europe PMC API 响应中的单条 result 对象。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            paper_id: str = str(item.get("id", "") or "")
            pmid: str = str(item.get("pmid", "") or "")
            pmcid: str = str(item.get("pmcid", "") or "")
            ext_source: str = str(item.get("source", "") or "")  # MED/PMC/AGR

            title: str = item.get("title", "") or ""
            abstract: str = item.get("abstractText", "") or ""
            doi: str | None = item.get("doi") or item.get("doiId") or None
            journal: str | None = item.get("journalTitle") or None

            # 作者解析：authorList.author[] -> [{fullName: "..."}]
            authors: list[Author] = []
            author_list = item.get("authorList") or {}
            for author_item in (
                author_list.get("author", []) if isinstance(author_list, dict) else []
            ):
                if isinstance(author_item, dict):
                    name = author_item.get("fullName") or author_item.get("collectiveName") or ""
                else:
                    name = str(author_item)
                if name:
                    authors.append(Author(name=name))

            # 发表年份与日期
            pub_year_raw = item.get("pubYear")
            year: int | None = None
            if pub_year_raw:
                try:
                    year = int(str(pub_year_raw)[:4])
                except (ValueError, TypeError):
                    year = None
            pub_date: str | None = (
                item.get("firstPublicationDate") or item.get("electronicPublicationDate") or None
            )

            # 引用数
            citation_count: int | None = None
            cc_raw = item.get("citedByCount")
            if cc_raw is not None:
                try:
                    citation_count = int(cc_raw)
                except (ValueError, TypeError):
                    citation_count = None

            # PDF / 全文 URL：在 fullTextUrlList.fullTextUrl[] 中过滤 documentStyle in (html, pdf)
            pdf_url: str | None = None
            html_url: str | None = None
            full_text_urls = item.get("fullTextUrlList") or {}
            ft_entries = (
                full_text_urls.get("fullTextUrl", []) if isinstance(full_text_urls, dict) else []
            )
            for ft in ft_entries:
                if not isinstance(ft, dict):
                    continue
                style = (ft.get("documentStyle") or "").lower()
                url = ft.get("url")
                if not url:
                    continue
                if style == "pdf" and not pdf_url:
                    pdf_url = url
                elif style == "html" and not html_url:
                    html_url = url

            # source_url：优先使用 PMC（有全文）→ PMID → Europe PMC 内部页
            if pmcid:
                source_url = f"https://europepmc.org/article/PMC/{pmcid}"
            elif pmid:
                source_url = f"https://europepmc.org/article/MED/{pmid}"
            elif paper_id and ext_source:
                source_url = f"https://europepmc.org/article/{ext_source}/{paper_id}"
            elif html_url:
                source_url = html_url
            else:
                source_url = "https://europepmc.org/"

            # 开放获取与关键词
            is_open_access = (item.get("isOpenAccess") or "").upper() == "Y"
            keyword_list = item.get("keywordList") or {}
            keywords = keyword_list.get("keyword", []) if isinstance(keyword_list, dict) else []

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source="europepmc",
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=citation_count,
                journal=journal,
                open_access_url=html_url if is_open_access else None,
                raw={
                    "id": paper_id,
                    "pmid": pmid or None,
                    "pmcid": pmcid or None,
                    "ext_source": ext_source or None,
                    "is_open_access": is_open_access,
                    "keywords": keywords[:20] if isinstance(keywords, list) else [],
                    "html_url": html_url,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 Europe PMC result 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        page_size: int = 10,
    ) -> SearchResponse:
        """使用 Europe PMC 检索文献。

        支持字段限定语法（拼接到 query 中），常用示例：
            - 年份范围：``(PUB_YEAR:[2020 TO 2024])``
            - 仅含全文：``(HAS_FT:Y)``
            - 仅开放获取：``(OPEN_ACCESS:Y)``
            - 限定来源：``(SRC:MED)`` / ``(SRC:PMC)`` / ``(SRC:AGR)``

        Args:
            query: 检索式。
            page_size: 返回结果数量（API 上限 1000）。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "query": query,
            "pageSize": min(max(page_size, 1), 1000),
            "format": "json",
            "resultType": "core",
            "cursorMark": "*",
        }

        resp = await self._client.get("/search", params=params)
        data: dict[str, Any] = resp.json()

        result_list = data.get("resultList") or {}
        items = result_list.get("result", []) if isinstance(result_list, dict) else []

        results: list[PaperResult] = []
        for item in items:
            try:
                results.append(self._parse_result(item))
            except ParseError as exc:
                logger.debug("跳过解析失败的 Europe PMC 论文: %s", exc)

        # hitCount 为字段名，而非 totalHits
        total_results: int
        try:
            total_results = int(data.get("hitCount", len(results)))
        except (ValueError, TypeError):
            total_results = len(results)

        return SearchResponse(
            query=query,
            total_results=total_results,
            page=1,
            per_page=page_size,
            results=results,
            source="europepmc",
        )


_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class EuropePmcClientProtocol(Protocol):
    async def search(self, query: str, page_size: int = 10) -> Any: ...


class EuropePmcSearchProvider(ClientSearchProvider):
    def __init__(self, client: EuropePmcClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, page_size=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "europepmc"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid Europe PMC response")
    return SearchPage(
        items=tuple(_item(paper, index) for index, paper in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("europepmc",), succeeded=("europepmc",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    identifier = getattr(paper, "raw", {}).get("id")
    parsed = urlsplit(getattr(paper, "source_url", ""))
    if (
        getattr(paper, "source", None) != "europepmc"
        or not isinstance(identifier, str)
        or _ID.fullmatch(identifier) is None
        or parsed.scheme != "https"
        or parsed.hostname != "europepmc.org"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.fragment
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid Europe PMC identifier")
    return SearchItem(
        id=f"europepmc:{identifier}",
        title=paper.title.strip(),
        url=paper.source_url,
        snippet=paper.abstract,
        rank=rank,
        provenance=(Provenance(provider="europepmc", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=paper.year,
            authors=tuple(author.name for author in paper.authors),
            identifiers=(SearchIdentifier(scheme="europepmc", value=identifier),),
            open_access=paper.raw.get("is_open_access"),
            citation_count=paper.citation_count,
        ),
    )


_SPEC = ClientSearchSpec("europepmc", "paper", _invoke, _project)


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无通道覆盖
    return EuropePmcSearchProvider(
        EuropePmcClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = EUROPEPMC_PROVIDER_MANIFEST
SPEC = EUROPEPMC_PROVIDER_SPEC
PROVIDER_TYPE = EuropePmcSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
