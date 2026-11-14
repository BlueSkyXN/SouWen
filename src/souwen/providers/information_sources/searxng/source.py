"""searxng（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from souwen.common_runtime.provider_support.exceptions import ConfigError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.config import get_config, SouWenConfig
from souwen.platform.provider_spec import (
    HttpOperation,
    ClientSearchProviderSpec,
    SelfHostedTransportDeclaration,
    ScraperSearchProvider,
)
from souwen.providers.runtime_clients.models import WebSearchResult, WebSearchResponse
from typing import Any


from souwen.platform.manifest_registry import ProviderManifest

SEARXNG_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "searxng",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "searxng-search",
                "capability": "search",
                "export": "SearXNGSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "searxng-self-hosted-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled", "base_url"],
        },
        "secrets": {"references": [], "optional_references": []},
        "network": {
            "egress_hosts": [],
            "target_egress": "configured_self_hosted_endpoint",
            "min_egress": "impersonate",
            "max_egress": "proxy",
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["searxng-self-hosted-provider-config-v1"],
        },
    }
)


SEARXNG_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="searxng",
    adapter_id="searxng-search",
    domain="web",
    adapter_reason="self-hosted JSON search parsing remains behind a strict Search bridge",
    transport=SelfHostedTransportDeclaration(
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    configuration_keys=("enabled", "base_url"),
)


logger = logging.getLogger("souwen.providers.runtime_clients.web.searxng")


class SearXNGClient(SouWenHttpClient):
    """SearXNG JSON API 客户端

    Args:
        instance_url: SearXNG 实例 URL (如 http://localhost:8888)
                     默认从 SOUWEN_SEARXNG_URL 环境变量读取
    """

    ENGINE_NAME = "searxng"

    def __init__(
        self,
        instance_url: str | None = None,
        *,
        follow_redirects: bool = True,
    ):
        if not instance_url:
            config = get_config()
            instance_url = config.resolve_base_url("searxng") or config.resolve_api_key(
                "searxng", "searxng_url"
            )
        self.instance_url = (instance_url or "").rstrip("/")
        if not self.instance_url:
            # 未提供实例 URL 时抛出配置错误
            raise ConfigError(
                "searxng_url",
                "SearXNG",
                "https://docs.searxng.org/admin/installation.html",
            )
        super().__init__(
            base_url=self.instance_url,
            source_name="searxng",
            follow_redirects=follow_redirects,
            resolve_source_base_url=False,
        )

    async def search(
        self,
        query: str,
        max_results: int = 20,
        engines: str | None = None,
        categories: str | None = None,
        language: str = "auto",
    ) -> WebSearchResponse:
        """通过 SearXNG JSON API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            engines: 指定引擎（逗号分隔，如 "google,bing,duckduckgo"）
            categories: 分类筛选（如 "general", "science", "news"）
            language: 语言（如 "zh-CN", "en-US", "auto"）
        """
        # 构建查询参数，format=json 指定 JSON 响应格式
        params: dict[str, Any] = {
            "q": query,
            "format": "json",
            "language": language,
        }
        # 可选的引擎和分类筛选
        if engines:
            params["engines"] = engines
        if categories:
            params["categories"] = categories

        # 发送 GET 请求到 SearXNG 实例
        resp = await self.get("/search", params=params)
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.common_runtime.provider_support.exceptions import ParseError

            raise ParseError(f"SearXNG 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取搜索结果
        for item in data.get("results", []):
            if len(results) >= max_results:
                break
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                # 跳过不完整的结果
                continue
            results.append(
                WebSearchResult(
                    source="searxng",
                    title=title,
                    url=url,
                    snippet=item.get("content", "").strip(),
                    engine=item.get("engine", self.ENGINE_NAME),  # 使用结果自带的引擎标识
                )
            )

        logger.info("SearXNG 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="searxng",
            results=results,
            total_results=data.get("number_of_results", 0)
            or len(results),  # 优先使用 API 返回的总数
        )


class SearXNGSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="searxng", domain="web", enabled=enabled)


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets
    from souwen.server.v2_runtime import _RuntimeClientAdapter

    source_timeout = config.get_source_config("searxng").timeout or config.timeout
    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=source_timeout,
        max_retries=config.max_retries,
    ):
        client = SearXNGClient(instance_url=str(configuration["base_url"]), follow_redirects=False)
    return SearXNGSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


def resolve_configuration(config: SouWenConfig) -> dict[str, object]:
    if not config.is_source_enabled("searxng", default=True):
        raise ValueError("provider is disabled")
    from souwen.platform.provider_spec import validate_self_hosted_base_url

    value = config.resolve_base_url("searxng", getattr(config, "searxng_url", None) or "")
    return {"enabled": True, "base_url": validate_self_hosted_base_url(value)}


MANIFEST = SEARXNG_PROVIDER_MANIFEST
SPEC = SEARXNG_PROVIDER_SPEC
PROVIDER_TYPE = SearXNGSearchProvider

# 自建实例地址来自这个旧版扁平配置字段（SPEC 7：声明驱动，源外不写字段名）。
SELF_HOSTED_CONFIG_FIELD = "searxng_url"


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SELF_HOSTED_CONFIG_FIELD", "SPEC", "build_provider"]
