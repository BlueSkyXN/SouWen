"""Composition root for the P4 target vertical slice."""

from __future__ import annotations

import inspect
import os
from collections.abc import Callable, Mapping
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
from souwen.modules.fetch.api import FetchModuleService
from souwen.modules.llm_search.api import LLMSearchModuleService
from souwen.modules.search.api import SearchModuleService
from souwen.modules.search.application import (
    OrderedSearchProviderSelector,
    SearchProviderSelection,
)
from souwen.paper.eric import EricClient
from souwen.paper.arxiv import ArxivClient
from souwen.paper.arxiv_fulltext import ArxivFulltextClient
from souwen.paper.biorxiv import BioRxivClient
from souwen.paper.crossref import CrossrefClient
from souwen.paper.dblp import DblpClient
from souwen.paper.europepmc import EuropePmcClient
from souwen.paper.hal import HalClient
from souwen.paper.huggingface import HuggingFaceClient
from souwen.paper.iacr import IacrClient
from souwen.paper.openalex import OpenAlexClient
from souwen.paper.osti import OstiClient
from souwen.paper.pmc import PmcClient
from souwen.paper.pubmed import PubMedClient
from souwen.patent.google_patents_scraper import GooglePatentsScraper
from souwen.patent.patentsview import PatentsViewClient
from souwen.platform.manifest_registry import ProviderManifest
from souwen.platform.provider_manager import ProviderManager
from souwen.platform.provider_spec import (
    ProviderSpec,
    RestJsonProviderSpec,
    resolve_provider_inputs,
    validate_spec_manifest,
)
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    ProviderRef,
    Provenance,
    RequestContext,
)
from souwen.providers.fetch_sources.arxiv_fulltext import (
    ARXIV_FULLTEXT_FETCH_PROFILE,
    ARXIV_FULLTEXT_PROVIDER_MANIFEST,
    ArxivFulltextFetchProvider,
)
from souwen.providers.fetch_sources.builtin import BUILTIN_FETCH_MANIFEST, BuiltinFetchProvider
from souwen.providers.information_sources.arxiv import (
    ARXIV_PROVIDER_MANIFEST,
    ARXIV_PROVIDER_SPEC,
    ArxivSearchProvider,
)
from souwen.providers.information_sources.biorxiv import (
    BIORXIV_PROVIDER_MANIFEST,
    BIORXIV_PROVIDER_SPEC,
    BioRxivSearchProvider,
)
from souwen.providers.information_sources.crossref import (
    CROSSREF_PROVIDER_MANIFEST,
    CROSSREF_PROVIDER_SPEC,
    CrossrefSearchProvider,
)
from souwen.providers.information_sources.dblp import (
    DBLP_PROVIDER_MANIFEST,
    DBLP_PROVIDER_SPEC,
    DblpSearchProvider,
)
from souwen.providers.information_sources.europepmc import (
    EUROPEPMC_PROVIDER_MANIFEST,
    EUROPEPMC_PROVIDER_SPEC,
    EuropePmcSearchProvider,
)
from souwen.providers.information_sources.google_patents import (
    GOOGLE_PATENTS_BRIDGE_SPEC,
    GOOGLE_PATENTS_PROVIDER_MANIFEST,
    GooglePatentsSearchProvider,
)
from souwen.providers.information_sources.hal import (
    HAL_PROVIDER_MANIFEST,
    HAL_PROVIDER_SPEC,
    HalSearchProvider,
)
from souwen.providers.information_sources.huggingface import (
    HUGGINGFACE_PROVIDER_MANIFEST,
    HUGGINGFACE_REST_SPEC,
    HuggingFaceSearchProvider,
)
from souwen.providers.information_sources.iacr import (
    IACR_BRIDGE_SPEC,
    IACR_PROVIDER_MANIFEST,
    IacrSearchProvider,
)
from souwen.providers.information_sources.openalex import (
    OPENALEX_PROVIDER_MANIFEST,
    OpenAlexSearchProvider,
)
from souwen.providers.information_sources.osti import (
    OSTI_BRIDGE_SPEC,
    OSTI_PROVIDER_MANIFEST,
    OstiSearchProvider,
)
from souwen.providers.information_sources.patentsview import (
    PATENTSVIEW_PROVIDER_MANIFEST,
    PATENTSVIEW_REST_SPEC,
    PatentsViewSearchProvider,
)
from souwen.providers.information_sources.eric import (
    ERIC_PROVIDER_MANIFEST,
    ERIC_REST_SPEC,
    EricSearchProvider,
)
from souwen.providers.information_sources.pmc import (
    PMC_BRIDGE_SPEC,
    PMC_PROVIDER_MANIFEST,
    PmcSearchProvider,
)
from souwen.providers.information_sources.pubmed import (
    PUBMED_BRIDGE_SPEC,
    PUBMED_PROVIDER_MANIFEST,
    PubMedSearchProvider,
)
from souwen.providers.llm_sources.uniapi_ark_annotations import (
    UNIAPI_ARK_MANIFESTS,
    UniApiArkAnnotationsDeepSeekProvider,
    UniApiArkAnnotationsDoubaoProvider,
)
from souwen.providers.llm_sources.uniapi_ark_annotations.manifest import (
    DEEPSEEK_ADAPTER_ID,
    DOUBAO_ADAPTER_ID,
)
from souwen.registry import defaults_for
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


class _LegacyRuntimeClient:
    """Give injected legacy clients one explicit, idempotent adapter-owned close surface."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def search(self, *args, **kwargs):
        return await self._client.search(*args, **kwargs)

    async def get_fulltext(self, *args, **kwargs):
        return await self._client.get_fulltext(*args, **kwargs)

    async def close(self) -> None:
        closer = getattr(self._client, "close", None)
        if closer is None:
            closer = getattr(getattr(self._client, "_client", None), "close", None)
        if closer is None:
            return
        result = closer()
        if inspect.isawaitable(result):
            await result


_BATCH_ONE_SEARCH_BINDINGS: tuple[
    tuple[ProviderManifest, ProviderSpec, type[Any], Callable[[Mapping[str, str]], Any]], ...
] = (
    (
        ARXIV_PROVIDER_MANIFEST,
        ARXIV_PROVIDER_SPEC,
        ArxivSearchProvider,
        lambda _secrets: ArxivClient(),
    ),
    (
        BIORXIV_PROVIDER_MANIFEST,
        BIORXIV_PROVIDER_SPEC,
        BioRxivSearchProvider,
        lambda _secrets: BioRxivClient(),
    ),
    (
        CROSSREF_PROVIDER_MANIFEST,
        CROSSREF_PROVIDER_SPEC,
        CrossrefSearchProvider,
        lambda _secrets: CrossrefClient(),
    ),
    (
        DBLP_PROVIDER_MANIFEST,
        DBLP_PROVIDER_SPEC,
        DblpSearchProvider,
        lambda _secrets: DblpClient(),
    ),
    (
        EUROPEPMC_PROVIDER_MANIFEST,
        EUROPEPMC_PROVIDER_SPEC,
        EuropePmcSearchProvider,
        lambda _secrets: EuropePmcClient(),
    ),
    (
        GOOGLE_PATENTS_PROVIDER_MANIFEST,
        GOOGLE_PATENTS_BRIDGE_SPEC,
        GooglePatentsSearchProvider,
        lambda _secrets: GooglePatentsScraper(),
    ),
    (
        HAL_PROVIDER_MANIFEST,
        HAL_PROVIDER_SPEC,
        HalSearchProvider,
        lambda _secrets: HalClient(),
    ),
    (
        HUGGINGFACE_PROVIDER_MANIFEST,
        HUGGINGFACE_REST_SPEC,
        HuggingFaceSearchProvider,
        lambda _secrets: HuggingFaceClient(),
    ),
    (
        IACR_PROVIDER_MANIFEST,
        IACR_BRIDGE_SPEC,
        IacrSearchProvider,
        lambda _secrets: IacrClient(),
    ),
    (
        OSTI_PROVIDER_MANIFEST,
        OSTI_BRIDGE_SPEC,
        OstiSearchProvider,
        lambda _secrets: OstiClient(),
    ),
    (
        PMC_PROVIDER_MANIFEST,
        PMC_BRIDGE_SPEC,
        PmcSearchProvider,
        lambda secrets: PmcClient(api_key=secrets.get("PUBMED_API_KEY")),
    ),
    (
        PUBMED_PROVIDER_MANIFEST,
        PUBMED_BRIDGE_SPEC,
        PubMedSearchProvider,
        lambda secrets: PubMedClient(api_key=secrets.get("PUBMED_API_KEY")),
    ),
)
_BATCH_ONE_MANIFEST_IDS = frozenset(
    manifest.id for manifest, _spec, _provider_type, _client_factory in _BATCH_ONE_SEARCH_BINDINGS
) | {ARXIV_FULLTEXT_PROVIDER_MANIFEST.id}
_LEGACY_DEFAULT_PROVIDER_IDS = frozenset(
    {
        *defaults_for("paper", "search"),
        *defaults_for("patent", "search"),
        *defaults_for("fetch", "fetch"),
    }
)


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
            if not config.is_source_enabled("patentsview", default=False):
                raise ValueError("provider is disabled")
            source = config.get_source_config("patentsview")
            configuration = {
                "enabled": True,
                "max_retries": config.max_retries,
                "timeout_seconds": source.timeout or config.timeout,
            }
            _validate_transport_configuration(configuration, provider_id="PatentsView")
            return configuration
        if manifest.id in _BATCH_ONE_MANIFEST_IDS:
            if not config.is_source_enabled(
                manifest.id, default=manifest.id in _LEGACY_DEFAULT_PROVIDER_IDS
            ):
                raise ValueError("provider is disabled")
            return {"enabled": True}
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
        if manifest.id in {"pmc", "pubmed"}:
            value = config.resolve_api_key("pubmed", "pubmed_api_key")
            return (
                {"PUBMED_API_KEY": value.strip()}
                if isinstance(value, str) and value.strip()
                else {}
            )
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


def _rest_transport(
    spec: RestJsonProviderSpec,
    manifest: ProviderManifest,
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
) -> tuple[dict[str, Any], HttpTransport]:
    """Build a fixed-endpoint transport from an already reviewed Provider spec."""
    validate_spec_manifest(spec, manifest)
    resolved_configuration, resolved_secrets = resolve_provider_inputs(spec, configuration, secrets)
    headers = {"User-Agent": f"SouWen/{__version__}"}
    if spec.auth.placement in {"header", "bearer"}:
        assert spec.auth.reference is not None and spec.auth.field_name is not None
        value = resolved_secrets.get(spec.auth.reference)
        if value is not None:
            headers[spec.auth.field_name] = (
                f"Bearer {value}" if spec.auth.placement == "bearer" else value
            )
    elif spec.auth.placement == "query":
        raise ValueError("query authentication requires an explicit reviewed client bridge")

    return resolved_configuration, HttpTransport(
        base_url=spec.base_url,
        headers=headers,
        timeout=resolved_configuration["timeout_seconds"],
        max_retries=resolved_configuration["max_retries"],
        proxy=None,
        follow_redirects=False,
    )


def _build_eric_provider(configuration, _secrets) -> EricSearchProvider:
    """Build ERIC only from the Provider Manager's resolved namespace."""
    _validate_eric_configuration(configuration)
    resolved_configuration, transport = _rest_transport(
        ERIC_REST_SPEC, ERIC_PROVIDER_MANIFEST, configuration, _secrets
    )
    return EricSearchProvider(
        EricClient(transport=transport),
        enabled=resolved_configuration["enabled"],
    )


def _build_patentsview_provider(configuration, secrets) -> PatentsViewSearchProvider:
    """Build PatentsView only from resolved config and secret namespaces."""
    _validate_transport_configuration(configuration, provider_id="PatentsView")
    resolved_configuration, transport = _rest_transport(
        PATENTSVIEW_REST_SPEC, PATENTSVIEW_PROVIDER_MANIFEST, configuration, secrets
    )
    return PatentsViewSearchProvider(
        PatentsViewClient(transport=transport),
        enabled=resolved_configuration["enabled"],
    )


def _catalog_items(
    config: SouWenConfig,
    manager: ProviderManager,
) -> tuple[ProviderCatalogItem, ...]:
    eligible = set(manager.eligible_adapter_ids)
    enabled_llm = set(config.enabled_uniapi_ark_source_ids())
    missing_gateway = config.missing_uniapi_gateway_fields()
    patentsview_enabled = config.is_source_enabled("patentsview", default=False)
    missing_patentsview = (
        ("patentsview_api_key",) if patentsview_enabled and not _patentsview_api_key(config) else ()
    )
    items: list[ProviderCatalogItem] = []
    for manifest in manager.registry.packages:
        adapter = manifest.adapters[0]
        provider_id = manifest.id
        adapter_id = adapter.id
        capability = adapter.capability
        if capability == "llm_search":
            enabled = provider_id in enabled_llm
        elif provider_id == "patentsview":
            enabled = patentsview_enabled
        elif provider_id in _BATCH_ONE_MANIFEST_IDS:
            enabled = config.is_source_enabled(
                provider_id, default=provider_id in _LEGACY_DEFAULT_PROVIDER_IDS
            )
        else:
            enabled = config.is_source_enabled(provider_id, default=True)
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
                capabilities=manifest.capabilities,
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
    validate_spec_manifest(ARXIV_FULLTEXT_FETCH_PROFILE, ARXIV_FULLTEXT_PROVIDER_MANIFEST)
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
    for manifest, _spec, provider_type, client_factory in _BATCH_ONE_SEARCH_BINDINGS:
        validate_spec_manifest(_spec, manifest)
        manager.register_factory(
            package_id=manifest.id,
            export=manifest.adapters[0].export,
            factory=lambda configuration, secrets, provider_type=provider_type, client_factory=client_factory: (
                provider_type(
                    _LegacyRuntimeClient(client_factory(secrets)),
                    enabled=configuration["enabled"],
                )
            ),
            provider_type=provider_type,
        )
    manager.register_factory(
        package_id=ARXIV_FULLTEXT_PROVIDER_MANIFEST.id,
        export="ArxivFulltextFetchProvider",
        factory=lambda configuration, _secrets: ArxivFulltextFetchProvider(
            _LegacyRuntimeClient(ArxivFulltextClient()),
            enabled=configuration["enabled"],
        ),
        provider_type=ArxivFulltextFetchProvider,
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
            *(
                manifest
                for manifest, _spec, _provider_type, _client_factory in _BATCH_ONE_SEARCH_BINDINGS
            ),
            ARXIV_FULLTEXT_PROVIDER_MANIFEST,
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
                    *(
                        SearchProviderSelection(
                            provider=ProviderRef(id=manifest.id, kind="search"),
                            adapter_id=manifest.adapters[0].id,
                            yaml_priority=priority,
                        )
                        for priority, (
                            manifest,
                            _spec,
                            _provider_type,
                            _client_factory,
                        ) in enumerate(
                            (
                                binding
                                for binding in _BATCH_ONE_SEARCH_BINDINGS
                                if binding[1].domain == "paper"
                            ),
                            start=3,
                        )
                    ),
                ),
                "patent": tuple(
                    SearchProviderSelection(
                        provider=ProviderRef(id=manifest.id, kind="search"),
                        adapter_id=manifest.adapters[0].id,
                        yaml_priority=priority,
                    )
                    for priority, (
                        manifest,
                        _spec,
                        _provider_type,
                        _client_factory,
                    ) in enumerate(
                        (
                            binding
                            for binding in _BATCH_ONE_SEARCH_BINDINGS
                            if binding[1].domain == "patent"
                        ),
                        start=1,
                    )
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
    fetch = FetchModuleService(
        manager,
        provider_adapter_ids={"arxiv_fulltext": "arxiv_fulltext-fetch"},
        browser_executor=browser_client,
    )
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
