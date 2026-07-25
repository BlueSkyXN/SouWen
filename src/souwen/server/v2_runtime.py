"""Composition root for the P4 target vertical slice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from souwen import __version__
from souwen.common_runtime.observability import get_request_id, get_source_sha
from souwen.common_runtime.transport import HttpTransport
from souwen.config import SouWenConfig
from souwen.delivery.api import (
    ProviderCatalogItem,
    ReadinessSnapshot,
    RolloutMode,
    RuntimeMetadata,
    TargetDeliveryServices,
)
from souwen.delivery.browser_worker_client import BrowserWorkerClient
from souwen.editions import source_policy
from souwen.modules.fetch.api import FetchModuleService
from souwen.modules.llm_search.api import LLMSearchModuleService
from souwen.modules.search.api import SearchModuleService
from souwen.modules.search.application import (
    OrderedSearchProviderSelector,
    SearchProviderSelection,
)
from souwen.paper.eric import EricClient
from souwen.paper.openalex import OpenAlexClient
from souwen.patent.patentsview import PatentsViewClient
from souwen.platform.provider_manager import ProviderManager
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    ProviderRef,
    Provenance,
    RequestContext,
)
from souwen.providers.fetch_sources.builtin import BUILTIN_FETCH_MANIFEST, BuiltinFetchProvider
from souwen.providers.information_sources.openalex import (
    OPENALEX_PROVIDER_MANIFEST,
    OpenAlexSearchProvider,
)
from souwen.providers.information_sources.patentsview import (
    PATENTSVIEW_PROVIDER_MANIFEST,
    PatentsViewSearchProvider,
)
from souwen.providers.information_sources.eric import ERIC_PROVIDER_MANIFEST, EricSearchProvider
from souwen.providers.llm_sources.uniapi_ark_annotations import (
    UNIAPI_ARK_MANIFESTS,
    UniApiArkAnnotationsDeepSeekProvider,
    UniApiArkAnnotationsDoubaoProvider,
)
from souwen.providers.llm_sources.uniapi_ark_annotations.manifest import (
    DEEPSEEK_ADAPTER_ID,
    DOUBAO_ADAPTER_ID,
)
from souwen.registry import get as get_legacy_source
from souwen.web.builtin import BuiltinFetcherClient
from souwen.worker.browser_fetch.protocol import BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST


class _OpenAlexRuntimeClient:
    """Expose the legacy client lifecycle through the injected adapter protocol."""

    def __init__(self, client: OpenAlexClient) -> None:
        self._client = client

    async def search(self, *args, **kwargs):
        return await self._client.search(*args, **kwargs)

    async def close(self) -> None:
        await self._client._client.close()


class _UnavailableLLMSearchModule:
    async def search(self, _request, _context, _execution):
        raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE)


@dataclass(slots=True)
class TargetRuntime:
    services: TargetDeliveryServices
    metadata: RuntimeMetadata
    manager: ProviderManager
    browser_client: BrowserWorkerClient | None

    async def close(self) -> None:
        failure: Exception | None = None
        try:
            await self.manager.close_all()
        except Exception as exc:
            failure = exc
        try:
            if self.browser_client is not None:
                await self.browser_client.close()
        except Exception as exc:
            if failure is None:
                failure = exc
        if failure is not None:
            raise failure


def _configuration_resolver(config: SouWenConfig):
    enabled_llm = set(config.enabled_uniapi_ark_source_ids())

    def resolve(manifest):
        if manifest.id == "openalex":
            if not config.is_source_enabled("openalex", default=True):
                raise ValueError("provider is disabled")
            return {"enabled": True}
        if manifest.id == "eric":
            if not config.is_source_enabled("eric", default=True):
                raise ValueError("provider is disabled")
            source = config.get_source_config("eric")
            configuration = {
                "enabled": True,
                "max_retries": config.max_retries,
                "timeout_seconds": source.timeout or config.timeout,
            }
            _validate_eric_configuration(configuration)
            return configuration
        if manifest.id == "patentsview":
            legacy = get_legacy_source("patentsview")
            if not source_policy(legacy, config.edition).available or not config.is_source_enabled(
                "patentsview", default=False
            ):
                raise ValueError("provider is disabled")
            source = config.get_source_config("patentsview")
            configuration = {
                "enabled": True,
                "max_retries": config.max_retries,
                "timeout_seconds": source.timeout or config.timeout,
            }
            _validate_transport_configuration(configuration, provider_id="PatentsView")
            return configuration
        if manifest.id == "builtin-fetch":
            if not config.is_source_enabled("builtin-fetch", default=True):
                raise ValueError("provider is disabled")
            return {"enabled": True}
        if manifest.id in {DEEPSEEK_ADAPTER_ID, DOUBAO_ADAPTER_ID}:
            if manifest.id not in enabled_llm:
                raise ValueError("provider is disabled")
            source = config.get_source_config(manifest.id)
            return {
                "enabled": True,
                "max_keyword": source.params.get("max_keyword", 10),
                "timeout_seconds": source.timeout or 45,
            }
        raise ValueError("unknown target provider")

    return resolve


def _secret_resolver(config: SouWenConfig):
    def resolve(manifest, _references):
        if manifest.id == "patentsview":
            return {"PATENTSVIEW_API_KEY": _patentsview_api_key(config)}
        if manifest.id not in {DEEPSEEK_ADAPTER_ID, DOUBAO_ADAPTER_ID}:
            return {}
        gateway = config.get_llm_search_gateway("uniapi")
        return {
            "UNIAPI_API_KEY": gateway.api_key or "",
            "UNIAPI_BASE_URL": gateway.base_url or "",
        }

    return resolve


def _patentsview_api_key(config: SouWenConfig) -> str:
    value = config.resolve_api_key("patentsview", "patentsview_api_key")
    return value.strip() if isinstance(value, str) else ""


def _browser_client() -> BrowserWorkerClient | None:
    token = os.environ.get("SOUWEN_BROWSER_WORKER_TOKEN")
    if token is None:
        return None
    port = os.environ.get("SOUWEN_BROWSER_WORKER_PORT", "49266").strip()
    config_revision = os.environ.get("SOUWEN_CONFIG_REVISION", "").strip() or None
    return BrowserWorkerClient(
        base_url=f"http://127.0.0.1:{port}",
        token=token,
        expected_source_sha=get_source_sha(),
        expected_config_revision=config_revision,
        expected_runtime_version=__version__,
        expected_inventory_digest=BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST,
    )


def _validate_transport_configuration(configuration, *, provider_id: str) -> None:
    """Validate bounded transport options during Provider Manager preflight."""
    timeout = configuration.get("timeout_seconds")
    max_retries = configuration.get("max_retries")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 0 < timeout <= 120
        or not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or not 0 <= max_retries <= 10
    ):
        raise ValueError(f"invalid {provider_id} transport configuration")


def _validate_eric_configuration(configuration) -> None:
    _validate_transport_configuration(configuration, provider_id="ERIC")


def _build_eric_provider(configuration, _secrets) -> EricSearchProvider:
    """Build ERIC only from the Provider Manager's resolved namespace."""
    _validate_eric_configuration(configuration)
    transport = HttpTransport(
        base_url="https://api.ies.ed.gov",
        headers={"User-Agent": f"SouWen/{__version__}"},
        timeout=configuration["timeout_seconds"],
        max_retries=configuration["max_retries"],
        proxy=None,
        follow_redirects=False,
    )
    return EricSearchProvider(
        EricClient(transport=transport),
        enabled=configuration["enabled"],
    )


def _build_patentsview_provider(configuration, secrets) -> PatentsViewSearchProvider:
    """Build PatentsView only from resolved config and secret namespaces."""
    _validate_transport_configuration(configuration, provider_id="PatentsView")
    api_key = secrets.get("PATENTSVIEW_API_KEY")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("missing PatentsView credential")
    api_key = api_key.strip()
    transport = HttpTransport(
        base_url="https://search.patentsview.org/api/v1",
        headers={
            "User-Agent": f"SouWen/{__version__}",
            "X-Api-Key": api_key,
        },
        timeout=configuration["timeout_seconds"],
        max_retries=configuration["max_retries"],
        proxy=None,
        follow_redirects=False,
    )
    return PatentsViewSearchProvider(
        PatentsViewClient(transport=transport),
        enabled=configuration["enabled"],
    )


def _catalog_items(
    config: SouWenConfig,
    manager: ProviderManager,
) -> tuple[ProviderCatalogItem, ...]:
    eligible = set(manager.eligible_adapter_ids)
    enabled_llm = set(config.enabled_uniapi_ark_source_ids())
    missing_gateway = config.missing_uniapi_gateway_fields()
    patentsview_enabled = config.is_source_enabled("patentsview", default=False)
    patentsview_policy_available = source_policy(
        get_legacy_source("patentsview"), config.edition
    ).available
    missing_patentsview = (
        ("patentsview_api_key",)
        if patentsview_policy_available and not _patentsview_api_key(config)
        else ()
    )
    declarations = (
        (
            "openalex",
            "openalex-search",
            "search",
            config.is_source_enabled("openalex", default=True),
        ),
        (
            "eric",
            "eric-search",
            "search",
            config.is_source_enabled("eric", default=True),
        ),
        (
            "patentsview",
            "patentsview-search",
            "search",
            patentsview_enabled,
        ),
        (
            "builtin-fetch",
            "builtin-fetch",
            "fetch",
            config.is_source_enabled("builtin-fetch", default=True),
        ),
        (
            DEEPSEEK_ADAPTER_ID,
            DEEPSEEK_ADAPTER_ID,
            "llm_search",
            DEEPSEEK_ADAPTER_ID in enabled_llm,
        ),
        (DOUBAO_ADAPTER_ID, DOUBAO_ADAPTER_ID, "llm_search", DOUBAO_ADAPTER_ID in enabled_llm),
    )
    items: list[ProviderCatalogItem] = []
    for provider_id, adapter_id, capability, enabled in declarations:
        if enabled and provider_id == "patentsview" and missing_patentsview:
            missing_fields = missing_patentsview
        elif enabled and capability == "llm_search" and missing_gateway:
            missing_fields = missing_gateway
        else:
            missing_fields = ()
        if adapter_id in eligible:
            reason = "available"
            status = "available"
        elif not enabled:
            reason = "disabled"
            status = "unavailable"
        elif missing_fields:
            reason = "missing_configuration"
            status = "unavailable"
        else:
            reason = "not_eligible"
            status = "unavailable"
        items.append(
            ProviderCatalogItem(
                provider=provider_id,
                capabilities=(capability,),
                availability=status,
                provenance=(
                    Provenance(
                        provider=provider_id,
                        outcome="success" if status == "available" else "failed",
                    ),
                ),
                reason=reason,
                missing_fields=missing_fields,
            )
        )
    return tuple(items)


def build_target_runtime(config: SouWenConfig) -> TargetRuntime:
    manager = ProviderManager(
        config_resolver=_configuration_resolver(config),
        secret_resolver=_secret_resolver(config),
    )
    manager.register_factory(
        package_id="openalex",
        export="OpenAlexSearchProvider",
        factory=lambda configuration, _secrets: OpenAlexSearchProvider(
            _OpenAlexRuntimeClient(
                OpenAlexClient(api_key=config.resolve_api_key("openalex", "openalex_api_key"))
            ),
            enabled=configuration["enabled"],
        ),
        provider_type=OpenAlexSearchProvider,
    )
    manager.register_factory(
        package_id="eric",
        export="EricSearchProvider",
        factory=_build_eric_provider,
        provider_type=EricSearchProvider,
    )
    manager.register_factory(
        package_id="patentsview",
        export="PatentsViewSearchProvider",
        factory=_build_patentsview_provider,
        provider_type=PatentsViewSearchProvider,
    )
    manager.register_factory(
        package_id="builtin-fetch",
        export="BuiltinFetchProvider",
        factory=lambda configuration, _secrets: BuiltinFetchProvider(
            BuiltinFetcherClient(respect_robots_txt=config.respect_robots_txt),
            enabled=configuration["enabled"],
        ),
        provider_type=BuiltinFetchProvider,
    )
    manager.register_factory(
        package_id=DEEPSEEK_ADAPTER_ID,
        export="UniApiArkAnnotationsDeepSeekProvider",
        factory=UniApiArkAnnotationsDeepSeekProvider,
        provider_type=UniApiArkAnnotationsDeepSeekProvider,
    )
    manager.register_factory(
        package_id=DOUBAO_ADAPTER_ID,
        export="UniApiArkAnnotationsDoubaoProvider",
        factory=UniApiArkAnnotationsDoubaoProvider,
        provider_type=UniApiArkAnnotationsDoubaoProvider,
    )
    manager.discover(
        (
            OPENALEX_PROVIDER_MANIFEST,
            ERIC_PROVIDER_MANIFEST,
            PATENTSVIEW_PROVIDER_MANIFEST,
            BUILTIN_FETCH_MANIFEST,
            *UNIAPI_ARK_MANIFESTS,
        )
    )

    search = SearchModuleService(
        manager,
        OrderedSearchProviderSelector(
            {
                "paper": (
                    SearchProviderSelection(
                        provider=ProviderRef(id="openalex", kind="search"),
                        adapter_id="openalex-search",
                        yaml_priority=1,
                    ),
                    SearchProviderSelection(
                        provider=ProviderRef(id="eric", kind="search"),
                        adapter_id="eric-search",
                        yaml_priority=2,
                    ),
                ),
            },
            explicit_selections=(
                SearchProviderSelection(
                    provider=ProviderRef(id="patentsview", kind="search"),
                    adapter_id="patentsview-search",
                    yaml_priority=1,
                ),
            ),
        ),
    )
    enabled_llm = config.enabled_uniapi_ark_source_ids()
    llm_search: Any = (
        LLMSearchModuleService(manager, enabled_llm[0])
        if enabled_llm
        else _UnavailableLLMSearchModule()
    )
    browser_client = _browser_client()
    fetch = FetchModuleService(manager, browser_executor=browser_client)
    required_adapters = {"openalex-search", "builtin-fetch"}

    async def readiness() -> ReadinessSnapshot:
        eligible = set(manager.eligible_adapter_ids)
        providers_ready = required_adapters.issubset(eligible)
        browser_ready = browser_client is None
        browser_status = "disabled"
        worker_source_sha = None
        if browser_client is not None:
            try:
                worker_receipt = await browser_client.readiness(
                    RequestContext(request_id=get_request_id()),
                    ExecutionContext.with_timeout(2),
                )
            except Exception:
                browser_status = "not_ready"
            else:
                browser_ready = True
                browser_status = "ready"
                worker_source_sha = worker_receipt.evidence.source_sha
        ready = providers_ready and browser_ready
        components = {
            "api": "ready",
            "openalex": "ready" if "openalex-search" in eligible else "not_ready",
            "builtin_fetch": "ready" if "builtin-fetch" in eligible else "not_ready",
            "llm_search": (
                "ready" if enabled_llm and enabled_llm[0] in eligible else "optional_unavailable"
            ),
            "browser_worker": browser_status,
        }
        return ReadinessSnapshot(
            ready=ready,
            components=components,
            error=None if ready else "required target runtime component is not ready",
            worker_source_sha=worker_source_sha,
        )

    metadata = RuntimeMetadata(
        version=__version__,
        source_sha=get_source_sha(),
        rollout_mode=RolloutMode.TARGET,
        config_revision=os.environ.get("SOUWEN_CONFIG_REVISION", "").strip() or None,
        wrapper_sha=os.environ.get("SOUWEN_WRAPPER_SHA", "").strip() or None,
    )
    services = TargetDeliveryServices(
        search=search,
        llm_search=llm_search,
        fetch=fetch,
        provider_items=_catalog_items(config, manager),
        readiness=readiness,
    )
    return TargetRuntime(
        services=services,
        metadata=metadata,
        manager=manager,
        browser_client=browser_client,
    )


__all__ = ["TargetRuntime", "build_target_runtime"]
