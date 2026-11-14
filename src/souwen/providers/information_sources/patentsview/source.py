"""patentsview（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import logging
import httpx
import re
from collections.abc import Mapping, Sequence
from souwen.common_runtime.provider_support.exceptions import ConfigError, NotFoundError, ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.common_runtime.provider_support.parsing import safe_parse_date
from souwen.common_runtime.provider_support.rate_limiter import TokenBucketLimiter
from souwen.common_runtime.transport import HttpTransport
from souwen.config import get_config, SouWenConfig
from souwen.platform.provider_spec import (
    RestJsonProviderSpec,
    ClientSearchProvider,
    ClientSearchSpec,
)
from souwen.platform.provider_spec.models import AuthDeclaration
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
from souwen.providers.runtime_clients.models import Applicant, PatentResult, SearchResponse
from typing import Any, Protocol
from urllib.parse import urlsplit


from souwen.platform.manifest_registry import ProviderManifest


PATENTSVIEW_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "patentsview",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "patentsview-search",
                "capability": "search",
                "export": "PatentsViewSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "patentsview-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled", "max_retries", "timeout_seconds"],
        },
        "secrets": {"references": ["PATENTSVIEW_API_KEY"]},
        "network": {
            "egress_hosts": ["search.patentsview.org"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["patentsview-provider-config-v1"],
        },
        # 免费 Key 源：默认关闭，配置 key 后启用（PRD 4.2）。
        "enabled_by_default": False,
    }
)


__all__ = ["PATENTSVIEW_PROVIDER_MANIFEST"]


PATENTSVIEW_REST_SPEC = RestJsonProviderSpec(
    provider_id="patentsview",
    adapter_id="patentsview-search",
    domain="patent",
    adapter_kind="client_adapter",
    review_status="reviewed_adapter",
    adapter_reason="existing patent response projection has not yet been expressed as generic mapping",
    host="search.patentsview.org",
    base_path="/api/v1",
    auth=AuthDeclaration(
        placement="header", reference="PATENTSVIEW_API_KEY", field_name="X-Api-Key"
    ),
    configuration_keys=("enabled", "max_retries", "timeout_seconds"),
)

__all__ = ["PATENTSVIEW_REST_SPEC"]


logger = logging.getLogger(__name__)

_DEFAULT_PATENT_FIELDS = [
    "patent_id",
    "patent_title",
    "patent_abstract",
    "patent_date",
    "patent_num_claims",
    "patent_type",
    "application_number",
    "application_filing_date",
    "assignees",
    "inventors",
    "cpcs",
    "ipcs",
]


class PatentsViewClient:
    """PatentsView API 客户端

    访问 PatentsView Search API。当前 API 要求通过 ``X-Api-Key`` 提供凭据。

    Attributes:
        BASE_URL: PatentsView API 基础地址
        RATE_LIMIT: 45 次/分钟 → 0.75 次/秒
    """

    BASE_URL = "https://search.patentsview.org/api/v1"
    RATE_LIMIT = 0.75  # 45 req/min

    def __init__(
        self,
        api_key: str | None = None,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        """初始化 PatentsView 客户端

        从参数或配置读取 API Key，初始化 HTTP 客户端和限流器。
        """
        if transport is None:
            cfg = get_config()
            resolved_key = api_key or cfg.resolve_api_key("patentsview", "patentsview_api_key")
            if not resolved_key:
                raise ConfigError(
                    key="patentsview_api_key",
                    service="PatentsView Search API",
                    register_url=(
                        "https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/"
                    ),
                )
            transport = SouWenHttpClient(
                base_url=self.BASE_URL,
                headers={"X-Api-Key": resolved_key},
                source_name="patentsview",
            )
        self._http = transport
        # 45 req/min 限制，约 0.75 req/s
        self._limiter = TokenBucketLimiter(rate=self.RATE_LIMIT, burst=3)

    async def __aenter__(self) -> PatentsViewClient:
        await self._http.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._http.__aexit__(*args)

    async def close(self) -> None:
        """关闭 HTTP 连接"""
        await self._http.close()

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: dict[str, Any],
        fields: list[str] | None = None,
        per_page: int = 10,
        page: int = 1,
        sort: list[dict[str, str]] | None = None,
    ) -> SearchResponse:
        """执行专利搜索

        Args:
            query: PatentsView JSON 查询过滤器，例如
                   ``{"_contains": {"patent_title": "neural network"}}``
            fields: 需返回的字段列表，默认使用 ``_DEFAULT_PATENT_FIELDS``
            per_page: 每页结果数
            page: 页码（从 1 开始）
            sort: 排序规则列表，例如 ``[{"patent_date": "desc"}]``

        Returns:
            SearchResponse 封装的搜索结果
        """
        payload: dict[str, Any] = {
            "q": query,
            "f": fields or _DEFAULT_PATENT_FIELDS,
            "o": {
                "size": per_page,
                "from": max(page - 1, 0) * per_page,
            },
        }
        if sort:
            payload["s"] = sort

        await self._limiter.acquire()
        resp = await self._http.post("/patent/", json=payload)
        data = self._parse_json(resp)

        # 逐项转换为标准 PatentResult
        patents = [self._to_patent_result(p) for p in data.get("patents", [])]
        total_results = data.get("total_patent_count")
        if total_results is None:
            total_results = data.get("total_hits")
        return SearchResponse(
            query=str(query),
            source="patentsview",
            total_results=total_results,
            results=patents,
            page=page,
            per_page=per_page,
        )

    async def get_patent(self, patent_id: str) -> PatentResult:
        """根据专利号获取详情

        Args:
            patent_id: USPTO 专利号，例如 ``"11234567"``

        Returns:
            PatentResult 模型

        Raises:
            NotFoundError: 未找到该专利
        """
        # 使用精确匹配查询单个专利
        query = {"_equals": {"patent_id": patent_id}}
        payload = {
            "q": query,
            "f": _DEFAULT_PATENT_FIELDS,
            "o": {"size": 1, "from": 0},
        }

        await self._limiter.acquire()
        resp = await self._http.post("/patent/", json=payload)
        data = self._parse_json(resp)

        patents = data.get("patents", [])
        if not patents:
            raise NotFoundError(f"专利 {patent_id} 未找到")
        return self._to_patent_result(patents[0])

    async def search_by_assignee(
        self,
        org_name: str,
        per_page: int = 10,
    ) -> SearchResponse:
        """按受让人/申请人组织名检索

        Args:
            org_name: 组织名称
            per_page: 每页结果数

        Returns:
            SearchResponse 封装的搜索结果
        """
        # 使用 _contains 进行模糊匹配组织名
        query = {"_contains": {"assignees.assignee_organization": org_name}}
        return await self.search(query, per_page=per_page)

    async def search_by_inventor(
        self,
        inventor_name: str,
        per_page: int = 10,
    ) -> SearchResponse:
        """按发明人姓名检索

        Args:
            inventor_name: 发明人姓名
            per_page: 每页结果数

        Returns:
            SearchResponse 封装的搜索结果
        """
        # 使用 _or 同时匹配名和姓
        query = {
            "_or": [
                {"_contains": {"inventors.inventor_first_name": inventor_name}},
                {"_contains": {"inventors.inventor_last_name": inventor_name}},
            ]
        }
        return await self.search(query, per_page=per_page)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict[str, Any]:
        """解析 JSON 响应"""
        try:
            return resp.json()
        except Exception as exc:
            raise ParseError(f"PatentsView 响应 JSON 解析失败: {exc}") from exc

    @staticmethod
    def _to_patent_result(raw: dict[str, Any]) -> PatentResult:
        """将 PatentsView 原始数据转换为 PatentResult 模型

        处理受让人、发明人、分类号等多种数据格式的转换。
        """
        # 受让人列表（可能为空）
        applicants: list[Applicant] = []
        for a in raw.get("assignees", []) or []:
            # 优先使用组织名，否则拼接姓名
            name = (
                a.get("assignee_organization")
                or f"{a.get('assignee_first_name', '')} {a.get('assignee_last_name', '')}".strip()
            )
            if name:
                applicants.append(Applicant(name=name, country=a.get("assignee_country")))

        # 发明人列表
        inventors: list[str] = []
        for inv in raw.get("inventors", []) or []:
            # 拼接姓名
            full = (
                f"{inv.get('inventor_first_name', '')} {inv.get('inventor_last_name', '')}".strip()
            )
            if full:
                inventors.append(full)

        # CPC / IPC 分类号列表
        cpc_codes = [
            c.get("cpc_group_id", "") for c in (raw.get("cpcs", []) or []) if c.get("cpc_group_id")
        ]
        ipc_codes = [
            i.get("ipc_group", "") for i in (raw.get("ipcs", []) or []) if i.get("ipc_group")
        ]

        patent_id = raw.get("patent_id", "")
        return PatentResult(
            source="patentsview",
            title=raw.get("patent_title", ""),
            patent_id=patent_id,
            application_number=raw.get("application_number"),
            publication_date=safe_parse_date(raw.get("patent_date")),
            filing_date=safe_parse_date(raw.get("application_filing_date")),
            applicants=applicants,
            inventors=inventors,
            abstract=raw.get("patent_abstract"),
            cpc_codes=cpc_codes,
            ipc_codes=ipc_codes,
            source_url=f"https://search.patentsview.org/patent/{patent_id}",
            raw=raw,
        )


_PROVIDER_ID = "patentsview"

_PATENT_ID_PATTERN = re.compile(r"^[A-Z0-9]+$")


class PatentsViewClientProtocol(Protocol):
    """Minimal PatentsView client surface injected by the composition root."""

    async def search(
        self,
        query: dict[str, Any],
        fields: list[str] | None = None,
        per_page: int = 10,
        page: int = 1,
        sort: list[dict[str, str]] | None = None,
    ) -> Any:
        """Return a normalized existing ``SearchResponse`` compatible object."""

    async def close(self) -> None:
        """Close the explicitly injected transport."""


class PatentsViewSearchProvider(ClientSearchProvider):
    """Search-only Provider v2 adapter for authenticated USPTO patent metadata."""

    capability = "search"

    def __init__(self, client: PatentsViewClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _PATENTSVIEW_BRIDGE_SPEC, enabled=enabled)


def _to_search_page(response: Any, *, limit: int, context: RequestContext) -> SearchPage:
    if getattr(response, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected existing response source")
    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    response_page = getattr(response, "page", None)
    response_limit = getattr(response, "per_page", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("invalid existing search results")
    if total is not None and (not isinstance(total, int) or isinstance(total, bool) or total < 0):
        raise ValueError("invalid existing result total")
    if response_page != 1 or response_limit != limit:
        raise ValueError("existing page does not match canonical request")
    if len(results) > limit:
        raise ValueError("existing result count exceeds canonical limit")
    if total is not None and total < len(results):
        raise ValueError("existing result total is smaller than the returned page")

    items = tuple(_to_search_item(item, rank=index) for index, item in enumerate(results, 1))
    return SearchPage(
        items=items,
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _to_search_item(patent: Any, *, rank: int) -> SearchItem:
    if getattr(patent, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected existing patent source")
    raw = getattr(patent, "raw", None)
    if not isinstance(raw, Mapping):
        raise ValueError("invalid existing patent attributes")
    patent_id = _patent_id(getattr(patent, "patent_id", None))
    source_url = _patent_url(getattr(patent, "source_url", None), patent_id)
    publication_date = getattr(patent, "publication_date", None)
    year = getattr(publication_date, "year", None) if publication_date is not None else None

    return SearchItem(
        id=f"patentsview:{patent_id}",
        title=_required_text(getattr(patent, "title", None)),
        url=source_url,
        snippet=_optional_text(getattr(patent, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_optional_year(year),
            identifiers=(SearchIdentifier(scheme="patentsview", value=patent_id),),
            resource_type="patent",
        ),
    )


def _patent_id(value: Any) -> str:
    identifier = _required_text(value).upper()
    if _PATENT_ID_PATTERN.fullmatch(identifier) is None:
        raise ValueError("invalid USPTO patent identifier")
    return identifier


def _patent_url(value: Any, patent_id: str) -> str:
    parsed = urlsplit(_required_text(value))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "search.patentsview.org"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path != f"/patent/{patent_id}"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid PatentsView record URL")
    return f"https://search.patentsview.org/patent/{patent_id}"


def _required_text(value: Any) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError("missing required text")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid text")
    normalized = value.strip()
    return normalized or None


def _optional_year(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
        raise ValueError("invalid publication year")
    return value


async def _bridge_invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(
        {"_contains": {"patent_title": request.query}}, per_page=limit, page=1
    )


def _bridge_project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    return _to_search_page(response, limit=limit, context=context)


_PATENTSVIEW_BRIDGE_SPEC = ClientSearchSpec(
    "patentsview", "patent", _bridge_invoke, _bridge_project
)

__all__ = ["PatentsViewClientProtocol", "PatentsViewSearchProvider"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del reviewed_proxy  # REST 固定端点，无通道覆盖
    from souwen.platform.provider_spec import resolve_provider_inputs
    from souwen.platform.provider_spec.validation import validate_spec_manifest

    validate_spec_manifest(PATENTSVIEW_REST_SPEC, PATENTSVIEW_PROVIDER_MANIFEST)
    resolved_configuration, resolved_secrets = resolve_provider_inputs(
        PATENTSVIEW_REST_SPEC, configuration, secrets
    )
    headers = {"User-Agent": "SouWen/3.0.0a1"}
    reference = PATENTSVIEW_REST_SPEC.auth.reference
    if reference is not None:
        value = resolved_secrets.get(reference)
        if value is not None:
            headers[PATENTSVIEW_REST_SPEC.auth.field_name] = value
    transport = HttpTransport(
        base_url=PATENTSVIEW_REST_SPEC.base_url,
        headers=headers,
        timeout=resolved_configuration["timeout_seconds"],
        max_retries=resolved_configuration["max_retries"],
        proxy=None,
        follow_redirects=False,
    )
    return PatentsViewSearchProvider(
        PatentsViewClient(transport=transport), enabled=resolved_configuration["enabled"]
    )


def resolve_configuration(config: SouWenConfig) -> dict[str, object]:
    if not config.is_source_enabled("patentsview", default=False):
        raise ValueError("provider is disabled")
    source = config.get_source_config("patentsview")
    timeout = source.timeout or config.timeout
    max_retries = config.max_retries
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 0 < timeout <= 120
        or not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or not 0 <= max_retries <= 10
    ):
        raise ValueError("invalid PatentsView transport configuration")
    return {"enabled": True, "max_retries": max_retries, "timeout_seconds": timeout}


MANIFEST = PATENTSVIEW_PROVIDER_MANIFEST
SPEC = PATENTSVIEW_REST_SPEC
PROVIDER_TYPE = PatentsViewSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
