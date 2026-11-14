"""github（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

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
from souwen.providers.runtime_clients.models import WebSearchResponse, WebSearchResult
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit


from souwen.platform.manifest_registry import ProviderManifest

GITHUB_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "github",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "github-search",
                "capability": "search",
                "export": "GitHubSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "github-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["GITHUB_TOKEN"]},
        "network": {
            "egress_hosts": ["api.github.com"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["github-provider-config-v1"],
        },
    }
)


GITHUB_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="github",
    adapter_id="github-search",
    domain="code",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="api.github.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/repositories"),),
    ),
    auth=AuthDeclaration(
        placement="header",
        reference="GITHUB_TOKEN",
        field_name="Authorization",
        required=False,
    ),
    configuration_keys=("enabled",),
)


logger = logging.getLogger("souwen.providers.runtime_clients.web.github")


class GitHubClient(SouWenHttpClient):
    """GitHub REST API 搜索客户端

    Args:
        token: GitHub Personal Access Token，默认从 SOUWEN_GITHUB_TOKEN /
               配置 ``github_token`` 读取；为空则使用未认证免费额度（10 req/min）
    """

    ENGINE_NAME = "github"
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None):
        # 从参数或配置读取 Token，未提供也允许（降级为未认证免费额度）
        config = get_config()
        self.token = (
            token if token is not None else config.resolve_api_key("github", "github_token")
        )

        # GitHub 推荐使用 v3 媒体类型并显式带 X-GitHub-Api-Version
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            # 提供 Token 时附带 Bearer 鉴权头
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            logger.debug("GitHub 未配置 Token，使用未认证模式（10 req/min）")

        super().__init__(
            base_url=self.BASE_URL,
            headers=headers,
            source_name="github",
        )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        sort: str = "stars",
        order: str = "desc",
    ) -> WebSearchResponse:
        """通过 GitHub Search API 搜索仓库

        Args:
            query: 搜索关键词，支持 GitHub 搜索语法
                  （如 ``"machine learning language:python stars:>1000"``）
            max_results: 最大返回结果数（API 单页上限 100）
            sort: 排序字段，可选 ``stars`` / ``forks`` / ``help-wanted-issues`` / ``updated``
            order: 排序方向，``desc`` 或 ``asc``
        """
        # GitHub Search API 单页上限 100，超出需要翻页（这里只取首页）
        per_page = min(max_results, 100)
        params: dict[str, Any] = {
            "q": query,
            "sort": sort,
            "order": order,
            "per_page": per_page,
        }

        resp = await self.get("/search/repositories", params=params)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.common_runtime.provider_support.exceptions import ParseError

            raise ParseError(f"GitHub 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("items", []):
            if len(results) >= max_results:
                break
            # 仓库标题使用 owner/repo 全名，URL 使用 html_url（用户访问页）
            full_name = (item.get("full_name") or "").strip()
            html_url = (item.get("html_url") or "").strip()
            if not full_name or not html_url:
                continue

            # 收集对排序/筛选有用的元数据，避免直接塞整个 item 增大体积
            raw: dict[str, Any] = {
                "stars": item.get("stargazers_count"),
                "forks": item.get("forks_count"),
                "language": item.get("language"),
                "updated_at": item.get("updated_at"),
                "topics": item.get("topics") or [],
                "open_issues": item.get("open_issues_count"),
                "license": (item.get("license") or {}).get("spdx_id"),
                "owner": (item.get("owner") or {}).get("login"),
                "archived": item.get("archived", False),
            }

            results.append(
                WebSearchResult(
                    source="github",
                    title=full_name,
                    url=html_url,
                    snippet=(item.get("description") or "").strip(),
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        total_count = data.get("total_count", len(results))
        logger.info("GitHub 返回 %d 条结果 (query=%s, total=%s)", len(results), query, total_count)

        return WebSearchResponse(
            query=query,
            source="github",
            results=results,
            total_results=len(results),
        )


_PROVIDER_ID = "github"


class GitHubClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...


class GitHubSearchProvider(ClientSearchProvider):
    def __init__(self, client: GitHubClientProtocol, *, enabled: bool = True) -> None:
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

__all__ = ["GitHubClientProtocol", "GitHubSearchProvider"]


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
        client = GitHubClient(token=secrets.get("GITHUB_TOKEN", ""))
    return GitHubSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = GITHUB_PROVIDER_MANIFEST
SPEC = GITHUB_PROVIDER_SPEC
PROVIDER_TYPE = GitHubSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
