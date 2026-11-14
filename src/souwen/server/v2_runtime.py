"""Composition root for the P4 target vertical slice."""

from __future__ import annotations

import inspect
import importlib
import os
import pkgutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, model_validator

from souwen import __version__
from souwen.common_runtime.observability import get_request_id, get_source_sha
from souwen.config import SouWenConfig
from souwen.server.browser_executor import InProcessBrowserFetchExecutor
from souwen.modules.fetch.api import FetchModuleService
from souwen.modules.fetch.application.orchestration import SiteHandler
from souwen.modules.search.api import SearchModuleService
from souwen.modules.search.application import (
    OrderedSearchProviderSelector,
    SearchProviderSelection,
)
from souwen.providers.runtime_clients.paper.openalex import OpenAlexClient
from souwen.platform.manifest_registry import ProviderManifest
from souwen.platform.provider_manager import ProviderManager
from souwen.platform.provider_spec import (
    ProviderSpec,
    validate_self_hosted_base_url,
    validate_spec_manifest,
)
from souwen.platform.provider_spi import (
    CanonicalModel,
    Capability,
    ExecutionContext,
    ProviderRef,
    Provenance,
    RequestContext,
    SearchRequest,
)
from souwen.providers.fetch_sources.jina_reader import (
    JINA_READER_FETCH_PROFILE,
    JINA_READER_PROVIDER_MANIFEST,
    JinaReaderFetchProvider,
)
from souwen.providers.fetch_sources.wayback import (
    WAYBACK_FETCH_PROVIDER_SPEC,
    WAYBACK_PROVIDER_MANIFEST,
    WaybackFetchProvider,
)
from souwen.providers.information_sources.github import (
    GITHUB_PROVIDER_MANIFEST,
    GITHUB_PROVIDER_SPEC,
    GitHubSearchProvider,
)
from souwen.providers.information_sources.stackoverflow import (
    STACKOVERFLOW_PROVIDER_MANIFEST,
    STACKOVERFLOW_PROVIDER_SPEC,
    StackOverflowSearchProvider,
)
from souwen.providers.information_sources.wikipedia import (
    WIKIPEDIA_PROVIDER_MANIFEST,
    WIKIPEDIA_PROVIDER_SPEC,
    WikipediaSearchProvider,
)
from souwen.providers.information_sources.youtube import (
    YOUTUBE_PROVIDER_MANIFEST,
    YOUTUBE_PROVIDER_SPEC,
    YouTubeSearchProvider,
)
from souwen.providers.runtime_clients.web.github import GitHubClient
from souwen.providers.runtime_clients.web.jina_reader import JinaReaderClient
from souwen.providers.runtime_clients.web.stackoverflow import StackOverflowClient
from souwen.providers.runtime_clients.web.wayback import WaybackClient
from souwen.providers.runtime_clients.web.wikipedia import WikipediaClient
from souwen.providers.runtime_clients.web.youtube import YouTubeClient


class _OpenAlexRuntimeClient:
    """Expose the existing client lifecycle through the injected adapter protocol."""

    def __init__(self, client: OpenAlexClient) -> None:
        self._client = client

    async def search(self, *args, **kwargs):
        return await self._client.search(*args, **kwargs)

    async def close(self) -> None:
        await self._client._client.close()


class _RuntimeClientAdapter:
    """Give injected existing clients one explicit, idempotent adapter-owned close surface."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def search(self, *args, **kwargs):
        return await self._client.search(*args, **kwargs)

    async def search_patents(self, *args, **kwargs):
        return await self._client.search_patents(*args, **kwargs)

    async def search_applications(self, *args, **kwargs):
        return await self._client.search_applications(*args, **kwargs)

    async def get_fulltext(self, *args, **kwargs):
        return await self._client.get_fulltext(*args, **kwargs)

    async def contents(self, *args, **kwargs):
        return await self._client.contents(*args, **kwargs)

    async def extract(self, *args, **kwargs):
        return await self._client.extract(*args, **kwargs)

    async def scrape(self, *args, **kwargs):
        return await self._client.scrape(*args, **kwargs)

    async def fetch(self, *args, **kwargs):
        return await self._client.fetch(*args, **kwargs)

    async def reader(self, *args, **kwargs):
        return await self._client.reader(*args, **kwargs)

    async def close(self) -> None:
        closer = getattr(self._client, "close", None)
        if closer is None:
            closer = getattr(getattr(self._client, "_client", None), "close", None)
        if closer is None:
            return
        result = closer()
        if inspect.isawaitable(result):
            await result


class _ManagedRuntimeClientAdapter(_RuntimeClientAdapter):
    """Enter existing async contexts lazily and close them exactly once."""

    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self._entered = False

    async def _ensure_entered(self) -> None:
        enter = getattr(self._client, "__aenter__", None)
        if not self._entered and enter is not None:
            await enter()
            self._entered = True

    async def fetch(self, *args, **kwargs):
        await self._ensure_entered()
        return await self._client.fetch(*args, **kwargs)

    async def close(self) -> None:
        exit_context = getattr(self._client, "__aexit__", None)
        if self._entered and exit_context is not None:
            self._entered = False
            await exit_context(None, None, None)
            return
        await super().close()


class ProviderCatalogItem(CanonicalModel):
    """Safe Provider v2 availability without config or secret values."""

    provider: str = Field(min_length=1, max_length=128)
    capabilities: tuple[Capability, ...] = Field(min_length=1)
    availability: Literal["available", "unavailable"]
    provenance: tuple[Provenance, ...] = Field(min_length=1)
    reason: Literal["available", "disabled", "missing_configuration", "not_eligible"]
    missing_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _status_matches_reason(self) -> ProviderCatalogItem:
        if (self.availability == "available") != (self.reason == "available"):
            raise ValueError("provider catalog status and reason do not match")
        if self.missing_fields and self.reason != "missing_configuration":
            raise ValueError("missing fields require missing_configuration")
        return self


@dataclass(frozen=True, slots=True)
class ReadinessSnapshot:
    """Readiness probe outcome consumed by the server app."""

    ready: bool
    components: dict[str, str]
    error: str | None = None
    worker_source_sha: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeMetadata:
    """Immutable runtime identity for probes."""

    version: str
    source_sha: str | None
    rollout_mode: Literal["target"] = "target"
    config_revision: str | None = None
    wrapper_sha: str | None = None


@dataclass(frozen=True, slots=True)
class TargetDeliveryServices:
    """Module services bundle owned by the target runtime."""

    search: Any
    fetch: Any
    provider_items: tuple[ProviderCatalogItem, ...]
    readiness: Any


_SELF_HOSTED_CONFIG_FIELDS = {
    "searxng": "searxng_url",
}


_BATCH_THREE_SEARCH_ONLY_BINDINGS: tuple[
    tuple[
        ProviderManifest,
        ProviderSpec,
        type[Any],
        Callable[[Mapping[str, object], Mapping[str, str]], Any],
    ],
    ...,
] = (
    (
        GITHUB_PROVIDER_MANIFEST,
        GITHUB_PROVIDER_SPEC,
        GitHubSearchProvider,
        lambda _configuration, secrets: GitHubClient(token=secrets.get("GITHUB_TOKEN", "")),
    ),
    (
        STACKOVERFLOW_PROVIDER_MANIFEST,
        STACKOVERFLOW_PROVIDER_SPEC,
        StackOverflowSearchProvider,
        lambda _configuration, secrets: StackOverflowClient(
            api_key=secrets.get("STACKOVERFLOW_API_KEY", "")
        ),
    ),
    (
        WIKIPEDIA_PROVIDER_MANIFEST,
        WIKIPEDIA_PROVIDER_SPEC,
        WikipediaSearchProvider,
        lambda _configuration, _secrets: WikipediaClient(),
    ),
    (
        YOUTUBE_PROVIDER_MANIFEST,
        YOUTUBE_PROVIDER_SPEC,
        YouTubeSearchProvider,
        lambda _configuration, secrets: YouTubeClient(api_key=secrets["YOUTUBE_API_KEY"]),
    ),
)

_BATCH_THREE_MULTI_BINDINGS: tuple[
    tuple[
        ProviderManifest,
        ProviderSpec,
        ProviderSpec,
        type[Any],
        type[Any],
        Callable[[Mapping[str, object], Mapping[str, str]], Any],
    ],
    ...,
] = ()

_BATCH_THREE_FETCH_ONLY_BINDINGS: tuple[
    tuple[
        ProviderManifest,
        ProviderSpec,
        type[Any],
        Callable[[Mapping[str, object], Mapping[str, str]], Any],
    ],
    ...,
] = (
    (
        JINA_READER_PROVIDER_MANIFEST,
        JINA_READER_FETCH_PROFILE,
        JinaReaderFetchProvider,
        lambda _configuration, secrets: JinaReaderClient(api_key=secrets.get("JINA_API_KEY")),
    ),
    (
        WAYBACK_PROVIDER_MANIFEST,
        WAYBACK_FETCH_PROVIDER_SPEC,
        WaybackFetchProvider,
        lambda _configuration, _secrets: WaybackClient(),
    ),
)
# 已迁移到 register 声明的源 = 全部发现到的 manifest（SPEC 7 后无批次概念）；
# 惰性求值避免模块加载期循环。
_MIGRATED_PROVIDER_IDS_CACHE: frozenset[str] | None = None


def _migrated_provider_ids() -> frozenset[str]:
    global _MIGRATED_PROVIDER_IDS_CACHE
    if _MIGRATED_PROVIDER_IDS_CACHE is None:
        _MIGRATED_PROVIDER_IDS_CACHE = frozenset(
            module.MANIFEST.id for module in _discover_register_modules()
        )
    return _MIGRATED_PROVIDER_IDS_CACHE


def _search_provider_declarations() -> tuple[tuple[ProviderManifest, Any], ...]:
    """Return the one reviewed manifest/spec declaration for every Search provider.

    声明来自每个源包的 register 模块（SPEC 7），此处无源 id 分派。
    """

    return tuple(
        (module.MANIFEST, getattr(module, "SPEC", None))
        for module in _discover_register_modules()
        if "search" in module.MANIFEST.capabilities
    )


def search_domains_by_provider() -> dict[str, str]:
    """Map every declared search provider id to its canonical domain."""

    return {spec.provider_id: spec.domain for _manifest, spec in _search_provider_declarations()}


def search_source_hosts() -> dict[str, str]:
    """Map every declared search provider id to its declared transport host."""

    hosts: dict[str, str] = {}
    for _manifest, spec in _search_provider_declarations():
        transport = getattr(spec, "transport", None)
        host = getattr(transport, "host", None)
        if host:
            hosts[spec.provider_id] = str(host)
    return hosts


def _build_search_selector(config: SouWenConfig) -> OrderedSearchProviderSelector:
    """Resolve the configured ordered defaults against reviewed Provider declarations."""

    declared: dict[str, tuple[str, str]] = {}
    declaration_order: dict[str, int] = {}
    for order, (manifest, spec) in enumerate(_search_provider_declarations(), start=1):
        validate_spec_manifest(spec, manifest)
        provider_id = spec.provider_id
        if manifest.id != provider_id or provider_id in declared:
            raise RuntimeError(f"invalid Search provider declaration: {provider_id}")
        search_adapters = tuple(
            adapter.id for adapter in manifest.adapters if adapter.capability == "search"
        )
        if len(search_adapters) != 1 or search_adapters[0] != spec.adapter_id:
            raise RuntimeError(f"Search adapter declaration mismatch: {provider_id}")
        declared[provider_id] = (spec.domain, search_adapters[0])
        declaration_order[provider_id] = order

    defaults_by_domain: dict[str, tuple[SearchProviderSelection, ...]] = {}
    configured_default_ids: set[str] = set()
    for domain, provider_ids in config.search_defaults.items():
        selections: list[SearchProviderSelection] = []
        for priority, provider_id in enumerate(provider_ids, start=1):
            declaration = declared.get(provider_id)
            if declaration is None:
                raise RuntimeError(f"unknown Search default provider: {provider_id}")
            provider_domain, adapter_id = declaration
            if provider_domain != domain:
                raise RuntimeError(
                    f"Search default provider {provider_id} belongs to {provider_domain}, not {domain}"
                )
            selections.append(
                SearchProviderSelection(
                    provider=ProviderRef(id=provider_id, kind="search"),
                    adapter_id=adapter_id,
                    yaml_priority=priority,
                )
            )
            configured_default_ids.add(provider_id)
        defaults_by_domain[domain] = tuple(selections)

    explicit_only = tuple(
        SearchProviderSelection(
            provider=ProviderRef(id=provider_id, kind="search"),
            adapter_id=adapter_id,
            yaml_priority=declaration_order[provider_id],
        )
        for provider_id, (_domain, adapter_id) in declared.items()
        if provider_id not in configured_default_ids
    )
    return OrderedSearchProviderSelector(
        defaults_by_domain,
        explicit_selections=explicit_only,
    )


_SELF_HOSTED_CONFIG_FIELDS: Mapping[str, str] = {"searxng": "searxng_url"}


def _self_hosted_provider_ids() -> frozenset[str]:
    """自建实例源：spec 声明 SelfHostedTransport（发现驱动，无源 id 清单）。"""

    from souwen.platform.provider_spec.models import SelfHostedTransportDeclaration

    return frozenset(
        module.MANIFEST.id
        for module in _discover_register_modules()
        if isinstance(
            getattr(getattr(module, "SPEC", None), "transport", None),
            SelfHostedTransportDeclaration,
        )
    )


def _self_hosted_base_url(config: SouWenConfig, provider_id: str) -> str:
    field = _SELF_HOSTED_CONFIG_FIELDS[provider_id]
    value = config.resolve_base_url(provider_id, getattr(config, field, None) or "")
    return validate_self_hosted_base_url(value)


@dataclass(slots=True)
class TargetRuntime:
    services: TargetDeliveryServices
    metadata: RuntimeMetadata
    manager: ProviderManager
    browser_client: InProcessBrowserFetchExecutor | None

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
    def resolve(manifest):
        register = _register_module_for(manifest.id)
        if register is None:
            raise ValueError("unknown target provider")
        hook = getattr(register, "resolve_configuration", None)
        if hook is not None:
            # 源声明了自己的配置解析（openalex/eric/patentsview/searxng）
            return hook(config)
        if not config.is_source_enabled(manifest.id, default=True):
            raise ValueError("provider is disabled")
        return {"enabled": True}

    return resolve


def _register_module_for(provider_id: str):
    for module in _discover_register_modules():
        if module.MANIFEST.id == provider_id:
            return module
    return None


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
        if _references:
            # 声明驱动（SPEC 7）：按 manifest 声明的 references 逐个解析，
            # 不再按批次集合分支。
            resolved: dict[str, str] = {}
            for reference in _references:
                field_name = reference.lower()
                if reference.endswith(("_SECRET", "_ACCOUNT_ID")):
                    value = getattr(config, field_name, None)
                else:
                    value = config.resolve_api_key(manifest.id, field_name)
                if isinstance(value, str) and value.strip():
                    resolved[reference] = value.strip()
            return resolved
        return {}

    return resolve


def _patentsview_api_key(config: SouWenConfig) -> str:
    value = config.resolve_api_key("patentsview", "patentsview_api_key")
    return value.strip() if isinstance(value, str) else ""


def _browser_client() -> InProcessBrowserFetchExecutor | None:
    """Browser Worker 已并入主进程（SPEC 5.6）：Playwright 可用即启用浏览器级。

    未安装 Playwright/Chromium 时返回 None，阶梯在前三级内工作，不报启动错误。
    """
    from souwen.common_runtime.provider_support.browser_fetch import chromium_available

    if not chromium_available():
        return None
    return InProcessBrowserFetchExecutor()


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


def _missing_provider_configuration(
    config: SouWenConfig, manifest: ProviderManifest
) -> tuple[str, ...]:
    """Return safe field names only; credential values never leave the resolver."""

    if manifest.id in _self_hosted_provider_ids():
        try:
            _self_hosted_base_url(config, manifest.id)
        except ValueError:
            return (_SELF_HOSTED_CONFIG_FIELDS[manifest.id],)
        return ()
    if manifest.id == "patentsview":
        return ("patentsview_api_key",) if not _patentsview_api_key(config) else ()
    if not manifest.secrets.references:
        return ()  # 无必填 secret 声明的源不存在缺配置问题
    resolved = _secret_resolver(config)(manifest, manifest.secrets.all_references)
    missing = [
        reference.lower() for reference in manifest.secrets.references if reference not in resolved
    ]
    return tuple(missing)


def _catalog_items(
    config: SouWenConfig,
    manager: ProviderManager,
) -> tuple[ProviderCatalogItem, ...]:
    eligible = set(manager.eligible_adapter_ids)
    patentsview_enabled = config.is_source_enabled("patentsview", default=False)
    items: list[ProviderCatalogItem] = []
    for manifest in manager.registry.packages:
        adapter = manifest.adapters[0]
        provider_id = manifest.id
        adapter_id = adapter.id
        if provider_id == "patentsview":
            enabled = patentsview_enabled
        elif provider_id in _migrated_provider_ids():
            enabled = config.is_source_enabled(provider_id, default=True)
        else:
            enabled = config.is_source_enabled(provider_id, default=True)
        if enabled:
            missing_fields = _missing_provider_configuration(config, manifest)
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


def _discover_register_modules() -> list[Any]:
    """目录发现全部源包的 register 模块（SPEC 7：新增源只动源目录）。"""

    modules: list[Any] = []
    for namespace in (
        "souwen.providers.information_sources",
        "souwen.providers.fetch_sources",
    ):
        package = importlib.import_module(namespace)
        for module_info in sorted(
            pkgutil.iter_modules(package.__path__), key=lambda item: item.name
        ):
            if not module_info.ispkg:
                continue
            module = importlib.import_module(f"{namespace}.{module_info.name}.register")
            if not all(
                hasattr(module, attr) for attr in ("MANIFEST", "PROVIDER_TYPE", "build_provider")
            ):
                raise RuntimeError(
                    f"provider register module is incomplete: {namespace}.{module_info.name}"
                )
            modules.append(module)
    if not modules:
        raise RuntimeError("no provider register modules discovered")
    return modules


def build_target_runtime(config: SouWenConfig) -> TargetRuntime:
    manager = ProviderManager(
        config_resolver=_configuration_resolver(config),
        secret_resolver=_secret_resolver(config),
    )

    # SPEC 7：统一注册循环——每个源的 manifest/spec/provider 构造来自
    # 它自己包里的 register.py；这里没有任何源 id 分支。
    register_modules = _discover_register_modules()
    fetch_adapter_ids: dict[str, str] = {}
    discovered_manifests: list[ProviderManifest] = []
    for module in register_modules:
        manifest = module.MANIFEST
        spec = getattr(module, "SPEC", None)
        if spec is not None:
            validate_spec_manifest(spec, manifest)
        reviewed_proxy = (
            config.resolve_proxy(manifest.id) if manifest.network.proxy_supported else None
        )
        build_provider = module.build_provider
        provider_type = module.PROVIDER_TYPE
        for adapter in manifest.adapters:
            manager.register_factory(
                package_id=manifest.id,
                export=adapter.export,
                factory=lambda configuration, secrets, build_provider=build_provider, cfg=config, proxy=reviewed_proxy: (
                    build_provider(configuration, secrets, cfg, proxy)
                ),
                provider_type=provider_type,
            )
            if adapter.capability == "fetch":
                fetch_adapter_ids[manifest.id] = adapter.id
        discovered_manifests.append(manifest)

    manager.discover(tuple(discovered_manifests))

    search_selector = _build_search_selector(config)
    search = SearchModuleService(
        manager,
        search_selector,
        provider_timeout=config.search_provider_timeout,
        request_budget=config.search_request_budget,
        demote_after=config.search_demote_after,
        demote_seconds=config.search_demote_seconds,
    )
    browser_client = _browser_client()

    # arxiv 站点处理器：URL 匹配 arxiv.org 论文页时先走专用全文源（SPEC 4.1）
    def _matches_arxiv_publication(target: str) -> bool:
        from urllib.parse import urlsplit

        parsed = urlsplit(target)
        return parsed.hostname == "arxiv.org" and any(
            parsed.path.startswith(prefix) for prefix in ("/abs/", "/pdf/", "/html/")
        )

    last_resort: list[tuple[str, str]] = [("wayback", "wayback-fetch")]
    if config.jina_fallback_enabled:
        last_resort.append(("jina_reader", "jina-reader-fetch"))
    fetch = FetchModuleService(
        manager,
        provider_adapter_ids=fetch_adapter_ids,
        browser_executor=browser_client,
        site_handlers=(
            SiteHandler(
                provider_id="arxiv_fulltext",
                adapter_id="arxiv_fulltext-fetch",
                matches=_matches_arxiv_publication,
            ),
        ),
        last_resort_providers=tuple(last_resort),
    )
    paper_primary = search_selector.select_default(
        SearchRequest(query="readiness", domains=("paper",))
    )[0]
    required_adapters = {paper_primary.adapter_id, "builtin-fetch"}

    async def readiness() -> ReadinessSnapshot:
        eligible = set(manager.eligible_adapter_ids)
        providers_ready = required_adapters.issubset(eligible)
        browser_ready = browser_client is None
        browser_status = "disabled"
        worker_source_sha = None
        if browser_client is not None:
            try:
                await browser_client.readiness(
                    RequestContext(request_id=get_request_id()),
                    ExecutionContext.with_timeout(2),
                )
            except Exception:
                browser_status = "not_ready"
            else:
                browser_ready = True
                browser_status = "ready"
        ready = providers_ready and browser_ready
        components = {
            "api": "ready",
            "crossref": "ready" if "crossref-search" in eligible else "not_ready",
            "openalex": "ready" if "openalex-search" in eligible else "not_ready",
            "builtin_fetch": "ready" if "builtin-fetch" in eligible else "not_ready",
            "browser_worker": browser_status,
        }
        components[paper_primary.provider.id] = (
            "ready" if paper_primary.adapter_id in eligible else "not_ready"
        )
        return ReadinessSnapshot(
            ready=ready,
            components=components,
            error=None if ready else "required target runtime component is not ready",
            worker_source_sha=worker_source_sha,
        )

    metadata = RuntimeMetadata(
        version=__version__,
        source_sha=get_source_sha(),
        config_revision=os.environ.get("SOUWEN_CONFIG_REVISION", "").strip() or None,
        wrapper_sha=os.environ.get("SOUWEN_WRAPPER_SHA", "").strip() or None,
    )
    services = TargetDeliveryServices(
        search=search,
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
