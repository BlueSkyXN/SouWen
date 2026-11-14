"""stackoverflow（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import html
import logging
from collections.abc import Sequence, Mapping
from hashlib import sha256
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.config import get_config, SouWenConfig
from souwen.platform.provider_spec import (
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
    ClientSearchProvider,
    ClientSearchSpec,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation
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
from souwen.providers.runtime_clients.models import WebSearchResult, WebSearchResponse
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit


from souwen.platform.manifest_registry import ProviderManifest

STACKOVERFLOW_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "stackoverflow",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "stackoverflow-search",
                "capability": "search",
                "export": "StackOverflowSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "stackoverflow-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["STACKOVERFLOW_API_KEY"]},
        "network": {
            "egress_hosts": ["api.stackexchange.com"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["stackoverflow-provider-config-v1"],
        },
    }
)


STACKOVERFLOW_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="stackoverflow",
    adapter_id="stackoverflow-search",
    domain="code",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="api.stackexchange.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/2.3/search/advanced"),),
    ),
    auth=AuthDeclaration(
        placement="query",
        reference="STACKOVERFLOW_API_KEY",
        field_name="key",
        required=False,
    ),
    configuration_keys=("enabled",),
)


logger = logging.getLogger("souwen.providers.runtime_clients.web.stackoverflow")


class StackOverflowClient(SouWenHttpClient):
    """StackOverflow（StackExchange）搜索客户端

    Args:
        api_key: StackExchange API Key，可选；
                 默认从 SOUWEN_STACKOVERFLOW_API_KEY 读取，
                 缺失时按匿名 IP 配额工作（约 300 次/天）
    """

    ENGINE_NAME = "stackoverflow"
    BASE_URL = "https://api.stackexchange.com/2.3"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key（可选）
        config = get_config()
        self.api_key = (
            api_key
            if api_key is not None
            else config.resolve_api_key("stackoverflow", "stackoverflow_api_key")
        )
        # 注意：StackExchange API 允许匿名调用，无 Key 时不抛 ConfigError
        super().__init__(base_url=self.BASE_URL, source_name="stackoverflow")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        site: str = "stackoverflow",
        sort: str = "relevance",
        order: str = "desc",
    ) -> WebSearchResponse:
        """通过 StackExchange API 搜索 StackOverflow 问答

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数 (API 上限 100)
            site: StackExchange 站点标识 (默认 "stackoverflow")
            sort: 排序字段 "relevance"/"votes"/"creation"/"activity"
            order: 排序方向 "desc" 或 "asc"
        """
        # 构建查询参数
        params: dict[str, Any] = {
            "q": query,
            "site": site,
            "pagesize": min(max_results, 100),  # API 单页上限 100
            "sort": sort,
            "order": order,
            "filter": "default",
        }
        # 有 Key 则附带，享受高配额（10000/天）
        if self.api_key:
            params["key"] = self.api_key

        # 发送 GET 请求；响应为 gzip，httpx 自动解压
        resp = await self.get("/search/advanced", params=params)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.common_runtime.provider_support.exceptions import ParseError

            raise ParseError(f"StackOverflow 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 解析 items 数组
        for item in data.get("items", []):
            if len(results) >= max_results:
                break
            # title 是 HTML 编码的（如 &amp; / &#39;），需还原
            title = html.unescape((item.get("title") or "").strip())
            url = (item.get("link") or "").strip()
            if not title or not url:
                # 跳过缺失关键字段的条目
                continue
            # 由 tags / score / answer_count 拼装可读 snippet
            tags = item.get("tags") or []
            score = item.get("score", 0)
            answer_count = item.get("answer_count", 0)
            is_answered = item.get("is_answered", False)
            answered_mark = "✓" if is_answered else "·"
            tags_part = f"[{', '.join(tags)}] " if tags else ""
            snippet = f"{tags_part}score={score}, answers={answer_count} {answered_mark}"
            # 完整元数据放入 raw
            raw: dict[str, Any] = {
                "question_id": item.get("question_id"),
                "score": score,
                "answer_count": answer_count,
                "tags": tags,
                "view_count": item.get("view_count"),
                "is_answered": is_answered,
                "creation_date": item.get("creation_date"),
                "last_activity_date": item.get("last_activity_date"),
                "accepted_answer_id": item.get("accepted_answer_id"),
            }
            # 过滤掉值为 None 的字段，保持 raw 紧凑
            raw = {k: v for k, v in raw.items() if v is not None}
            results.append(
                WebSearchResult(
                    source="stackoverflow",
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        # 记录配额信息（便于诊断 429）
        quota_remaining = data.get("quota_remaining")
        has_more = data.get("has_more")
        if quota_remaining is not None:
            logger.debug(
                "StackOverflow quota_remaining=%s has_more=%s",
                quota_remaining,
                has_more,
            )

        logger.info("StackOverflow 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="stackoverflow",
            results=results,
            total_results=len(results),
        )


_PROVIDER_ID = "stackoverflow"


class StackOverflowClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...


class StackOverflowSearchProvider(ClientSearchProvider):
    def __init__(self, client: StackOverflowClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, max_results=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != _PROVIDER_ID
        or getattr(response, "page", None) != 1
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid existing web search response")
    return SearchPage(
        items=tuple(_item(result, rank) for rank, result in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(result: Any, rank: int) -> SearchItem:
    if (
        getattr(result, "source", None) != _PROVIDER_ID
        or not isinstance(getattr(result, "title", None), str)
        or not result.title.strip()
    ):
        raise ValueError("invalid existing web result")
    url = _canonical_url(getattr(result, "url", None))
    identifier = sha256(url.encode("utf-8")).hexdigest()
    return SearchItem(
        id=f"{_PROVIDER_ID}:{identifier}",
        title=result.title.strip(),
        url=url,
        snippet=_optional_text(getattr(result, "snippet", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            identifiers=(SearchIdentifier(scheme=_PROVIDER_ID, value=identifier),)
        ),
    )


def _canonical_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing record URL")
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("invalid record URL")
    host = parsed.hostname.lower()
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid snippet")
    return value.strip() or None


_SPEC = ClientSearchSpec(_PROVIDER_ID, "code", _invoke, _project)

__all__ = ["StackOverflowClientProtocol", "StackOverflowSearchProvider"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    from souwen.server.v2_runtime import _RuntimeClientAdapter

    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        client = StackOverflowClient(api_key=secrets.get("STACKOVERFLOW_API_KEY", ""))
    return StackOverflowSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = STACKOVERFLOW_PROVIDER_MANIFEST
SPEC = STACKOVERFLOW_PROVIDER_SPEC
PROVIDER_TYPE = StackOverflowSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
