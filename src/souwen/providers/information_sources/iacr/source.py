"""iacr（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import logging
import re
from bs4 import BeautifulSoup
from collections.abc import Sequence, Mapping
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
from urllib.parse import quote, urlsplit


from souwen.platform.manifest_registry import ProviderManifest


IACR_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "iacr",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "iacr-search",
                "capability": "search",
                "export": "IacrSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "iacr-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["eprint.iacr.org"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["iacr-provider-config-v1"],
        },
    }
)

__all__ = ["IACR_PROVIDER_MANIFEST"]


IACR_BRIDGE_SPEC = ClientSearchProviderSpec(
    provider_id="iacr",
    adapter_id="iacr-search",
    adapter_reason="HTML selector parsing remains in the existing IACR scraper bridge",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="eprint.iacr.org",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["IACR_BRIDGE_SPEC"]


logger = logging.getLogger(__name__)

_BASE_URL = "https://eprint.iacr.org"

_DEFAULT_RPS = 0.5

_PAPER_ID_RE = re.compile(r"/?(\d{4}/\d+)")

_AUTHOR_AND_RE = re.compile(r"\s+and\s+", re.IGNORECASE)


class IacrClient:
    """IACR ePrint 密码学预印本搜索客户端（实验性）。

    特点:
        - 无需 API Key，零配置即用
        - 密码学 / 安全 / 理论领域的权威预印本来源
        - 通过 HTML 抓取实现，**实验性**——页面结构变更时可能失效
        - 不二次抓取详情页，所有字段从搜索结果块解析

    Warning:
        实验性数据源。IACR 调整页面 CSS / DOM 时本客户端可能停止工作，
        请定期校验 selectors 与抽取逻辑。
    """

    def __init__(self) -> None:
        """初始化 IACR ePrint 搜索客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="iacr")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=1)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> IacrClient:
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
    def _split_authors(raw: str) -> list[Author]:
        """拆分作者字符串为 Author 列表，先按 ' and ' 再按 ','。"""
        if not raw:
            return []
        parts: list[str] = []
        for chunk in _AUTHOR_AND_RE.split(raw):
            parts.extend(p.strip() for p in chunk.split(",") if p.strip())
        return [Author(name=name) for name in parts if name]

    @staticmethod
    def _extract_paper_id(block: Any) -> str | None:
        """从结果块中提取 paper_id（形如 '2025/1014'）。

        优先匹配 a.paperlink，否则回退扫描所有 <a> 标签。
        """
        anchor = block.select_one("a.paperlink")
        if anchor and anchor.get("href"):
            match = _PAPER_ID_RE.search(anchor["href"])
            if match:
                return match.group(1)

        for a in block.find_all("a", href=True):
            match = _PAPER_ID_RE.search(a["href"])
            if match:
                return match.group(1)
        return None

    @classmethod
    def _parse_result_block(cls, block: Any) -> PaperResult | None:
        """将单个搜索结果 HTML 块解析为 PaperResult。

        Args:
            block: BeautifulSoup Tag，对应一个 div.mb-4 结果容器。

        Returns:
            PaperResult；若关键字段（paper_id / title）缺失则返回 None。
        """
        try:
            paper_id = cls._extract_paper_id(block)
            if not paper_id:
                return None

            # 标题：第一个 <strong>
            title_tag = block.find("strong")
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                # 退化方案：使用 paperlink 锚点文本
                anchor = block.select_one("a.paperlink")
                if anchor:
                    title = anchor.get_text(strip=True)
            if not title:
                return None

            # 作者
            authors_tag = block.select_one("span.fst-italic")
            authors: list[Author] = []
            if authors_tag:
                authors = cls._split_authors(authors_tag.get_text(" ", strip=True))

            # 摘要
            abstract_tag = block.select_one("p.search-abstract")
            abstract: str | None = None
            if abstract_tag:
                abstract = abstract_tag.get_text(" ", strip=True) or None

            # 类别 / 主题（可能多个 badge）
            badges = block.select("small.badge")
            categories = [b.get_text(strip=True) for b in badges if b.get_text(strip=True)]
            venue: str | None = ", ".join(categories) if categories else None

            # 最近更新日期文本（可选信息，留存于 raw）
            updated_tag = block.select_one("small.ms-auto")
            last_updated = updated_tag.get_text(strip=True) if updated_tag else None

            # 年份从 paper_id 前 4 位提取
            year: int | None = None
            try:
                year = int(paper_id.split("/", 1)[0])
            except (ValueError, IndexError):
                year = None

            source_url = f"{_BASE_URL}/{paper_id}"
            pdf_url = f"{_BASE_URL}/{paper_id}.pdf"

            return PaperResult(
                source="iacr",
                title=title,
                authors=authors,
                abstract=abstract,
                doi=None,
                year=year,
                publication_date=None,
                venue=venue,
                citation_count=None,
                source_url=source_url,
                pdf_url=pdf_url,
                raw={
                    "paper_id": paper_id,
                    "categories": categories,
                    "last_updated": last_updated,
                },
            )
        except Exception as exc:
            logger.debug("IACR 单条结果解析失败，跳过: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> SearchResponse:
        """搜索 IACR ePrint 密码学预印本归档。

        Note:
            **实验性数据源**：本方法通过 HTML 抓取实现。
            如果 IACR 调整页面结构（CSS class / DOM 层级），结果可能为空或异常。

        Args:
            query: 搜索关键词。
            max_results: 最大返回结果数。

        Returns:
            SearchResponse 包含 PaperResult 列表。
        """
        await self._limiter.acquire()

        encoded_query = quote(query, safe="")
        resp = await self._client.get(f"/search?q={encoded_query}")

        soup = BeautifulSoup(resp.text, "lxml")

        # 主选择器：div.mb-4。若未命中，回退为含 a.paperlink 的最近祖先 div。
        blocks = soup.select("div.mb-4")
        if not blocks:
            anchors = soup.select("a.paperlink")
            seen: set[int] = set()
            blocks = []
            for a in anchors:
                parent = a.find_parent("div")
                if parent is not None and id(parent) not in seen:
                    seen.add(id(parent))
                    blocks.append(parent)

        results: list[PaperResult] = []
        for block in blocks:
            if len(results) >= max_results:
                break
            paper = self._parse_result_block(block)
            if paper:
                results.append(paper)

        return SearchResponse(
            query=query,
            total_results=len(results),
            page=1,
            per_page=max_results,
            results=results,
            source="iacr",
        )


_PROVIDER_ID = "iacr"

_PAPER_ID = re.compile(r"^\d{4}/\d+$")


class IacrClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...
    async def close(self) -> None: ...


class IacrSearchProvider(ClientSearchProvider):
    capability = "search"

    def __init__(self, client: IacrClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE_SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, max_results=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    if getattr(response, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected existing response source")
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or total != len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid IACR search response")
    return SearchPage(
        items=tuple(_item(value, index) for index, value in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(value: Any, rank: int) -> SearchItem:
    if getattr(value, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected existing paper source")
    raw = getattr(value, "raw", None)
    identifier = raw.get("paper_id") if isinstance(raw, dict) else None
    if not isinstance(identifier, str) or _PAPER_ID.fullmatch(identifier) is None:
        raise ValueError("invalid IACR paper identifier")
    url = urlsplit(_text(getattr(value, "source_url", None)))
    if (
        url.scheme != "https"
        or url.hostname != "eprint.iacr.org"
        or url.path != f"/{identifier}"
        or url.username
        or url.password
        or url.port
        or url.query
        or url.fragment
    ):
        raise ValueError("invalid IACR record URL")
    year = getattr(value, "year", None)
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid paper year")
    authors = tuple(
        _text(getattr(author, "name", None)) for author in getattr(value, "authors", ())
    )
    if len(authors) != len(set(authors)):
        raise ValueError("duplicate IACR authors")
    return SearchItem(
        id=f"iacr:{identifier}",
        title=_text(getattr(value, "title", None)),
        url=f"https://eprint.iacr.org/{identifier}",
        snippet=_optional_text(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            authors=authors,
            identifiers=(SearchIdentifier(scheme="iacr", value=identifier),),
            resource_type="preprint",
        ),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


def _text(value: Any) -> str:
    result = _optional_text(value)
    if result is None:
        raise ValueError("missing text")
    return result


_BRIDGE_SPEC = ClientSearchSpec(_PROVIDER_ID, "paper", _invoke, _project)

assert IACR_BRIDGE_SPEC.adapter_kind == "client_adapter"

__all__ = ["IacrClientProtocol", "IacrSearchProvider"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无通道覆盖
    return IacrSearchProvider(
        IacrClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = IACR_PROVIDER_MANIFEST
SPEC = IACR_BRIDGE_SPEC
PROVIDER_TYPE = IacrSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
