"""coolapk（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

from collections.abc import Mapping
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import (
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
    CnScraperBinding,
    CnScraperSearchProvider,
)
from souwen.platform.provider_spec.models import HttpOperation
from souwen.providers.runtime_clients.web._ddg_site_search import DdgSiteSearchClient
from souwen.providers.runtime_clients.web.duckduckgo import DuckDuckGoClient
from typing import Any, Protocol


from souwen.platform.manifest_registry import ProviderManifest

COOLAPK_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "coolapk",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "coolapk-search",
                "capability": "search",
                "export": "CoolapkSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "coolapk-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["html.duckduckgo.com"],
            "min_egress": "impersonate",
            "max_egress": "browser",
            "proxy_supported": True,
            "browser_required": True,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["coolapk-provider-config-v1"],
        },
    }
)
__all__ = ["COOLAPK_PROVIDER_MANIFEST"]


COOLAPK_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="coolapk",
    adapter_id="coolapk-search",
    domain="community",
    adapter_reason="DDG HTML site-search and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="html.duckduckgo.com",
        protocol="html",
        operations=(HttpOperation(method="POST", endpoint="/html/"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["COOLAPK_PROVIDER_SPEC"]


class CoolapkClient(DdgSiteSearchClient):
    ENGINE_NAME = "coolapk"
    SITE_DOMAIN = "coolapk.com"
    SOURCE_TYPE = "coolapk"


_BINDING = CnScraperBinding("coolapk", "community", result_host="coolapk.com")


class CoolapkClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 20) -> Any: ...
    async def close(self) -> None: ...


class CoolapkSearchProvider(CnScraperSearchProvider):
    def __init__(self, client: CoolapkClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BINDING, enabled=enabled)


def create_coolapk_client() -> Any:
    from souwen.providers.runtime_clients.web.coolapk import CoolapkClient

    return CoolapkClient()


__all__ = ["CoolapkClientProtocol", "CoolapkSearchProvider", "create_coolapk_client"]


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
        client = CoolapkClient(follow_redirects=False)
    client._ddg_client = DuckDuckGoClient()
    return CoolapkSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = COOLAPK_PROVIDER_MANIFEST
SPEC = COOLAPK_PROVIDER_SPEC
PROVIDER_TYPE = CoolapkSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
