"""Composition root for the P4 target vertical slice."""

from __future__ import annotations

import inspect
import importlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from souwen import __version__
from souwen.providers.runtime_clients.book.doab import DOABClient
from souwen.providers.runtime_clients.book.internet_archive import InternetArchiveClient
from souwen.providers.runtime_clients.book.library_of_congress import LibraryOfCongressClient
from souwen.providers.runtime_clients.book.open_library import OpenLibraryClient
from souwen.providers.runtime_clients.book.wikisource import WikisourceClient
from souwen.common_runtime.observability import get_request_id, get_source_sha
from souwen.common_runtime.transport import HttpTransport
from souwen.config import SouWenConfig
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from souwen.delivery.api import (
    ProviderCatalogItem,
    ReadinessSnapshot,
    RuntimeMetadata,
    TargetDeliveryServices,
)
from souwen.delivery.browser_worker_client import BrowserWorkerClient
from souwen.modules.fetch.api import FetchModuleService
from souwen.modules.search.api import SearchModuleService
from souwen.modules.search.application import (
    OrderedSearchProviderSelector,
    SearchProviderSelection,
)
from souwen.providers.runtime_clients.paper.eric import EricClient
from souwen.providers.runtime_clients.paper.arxiv import ArxivClient
from souwen.providers.runtime_clients.paper.arxiv_fulltext import ArxivFulltextClient
from souwen.providers.runtime_clients.paper.biorxiv import BioRxivClient
from souwen.providers.runtime_clients.paper.crossref import CrossrefClient
from souwen.providers.runtime_clients.paper.europepmc import EuropePmcClient
from souwen.providers.runtime_clients.paper.doaj import DoajClient
from souwen.providers.runtime_clients.paper.hal import HalClient
from souwen.providers.runtime_clients.paper.huggingface import HuggingFaceClient
from souwen.providers.runtime_clients.paper.iacr import IacrClient
from souwen.providers.runtime_clients.paper.openalex import OpenAlexClient
from souwen.providers.runtime_clients.paper.openaire import OpenAireClient
from souwen.providers.runtime_clients.paper.osti import OstiClient
from souwen.providers.runtime_clients.paper.pmc import PmcClient
from souwen.providers.runtime_clients.paper.pubmed import PubMedClient
from souwen.providers.runtime_clients.paper.semantic_scholar import SemanticScholarClient
from souwen.providers.runtime_clients.paper.zenodo import ZenodoClient
from souwen.providers.runtime_clients.patent.epo_ops import EpoOpsClient
from souwen.providers.runtime_clients.patent.google_patents_scraper import GooglePatentsScraper
from souwen.providers.runtime_clients.patent.patentsview import PatentsViewClient
from souwen.providers.runtime_clients.patent.uspto_odp import UsptoOdpClient
from souwen.platform.manifest_registry import ProviderManifest
from souwen.platform.provider_manager import ProviderManager
from souwen.platform.provider_spec import (
    ClientSearchProvider,
    ClientSearchProviderSpec,
    ProviderSpec,
    RestJsonProviderSpec,
    resolve_provider_inputs,
    validate_self_hosted_base_url,
    validate_spec_manifest,
)
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderRef,
    Provenance,
    RequestContext,
    SearchRequest,
)
from souwen.providers.fetch_sources.arxiv_fulltext import (
    ARXIV_FULLTEXT_FETCH_PROFILE,
    ARXIV_FULLTEXT_PROVIDER_MANIFEST,
    ArxivFulltextFetchProvider,
)
from souwen.providers.fetch_sources.builtin import BUILTIN_FETCH_MANIFEST, BuiltinFetchProvider
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
from souwen.providers.information_sources.doaj import (
    DOAJ_PROVIDER_MANIFEST,
    DOAJ_PROVIDER_SPEC,
    DoajSearchProvider,
)
from souwen.providers.information_sources.europepmc import (
    EUROPEPMC_PROVIDER_MANIFEST,
    EUROPEPMC_PROVIDER_SPEC,
    EuropePmcSearchProvider,
)
from souwen.providers.information_sources.epo_ops import (
    EPO_OPS_BRIDGE_SPEC,
    EPO_OPS_PROVIDER_MANIFEST,
    EpoOpsSearchProvider,
)
from souwen.providers.information_sources.google_patents import (
    GOOGLE_PATENTS_BRIDGE_SPEC,
    GOOGLE_PATENTS_PROVIDER_MANIFEST,
    GooglePatentsSearchProvider,
)
from souwen.providers.information_sources.github import (
    GITHUB_PROVIDER_MANIFEST,
    GITHUB_PROVIDER_SPEC,
    GitHubSearchProvider,
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
    OPENALEX_REST_SPEC,
    OpenAlexSearchProvider,
)
from souwen.providers.information_sources.openaire import (
    OPENAIRE_PROVIDER_MANIFEST,
    OPENAIRE_PROVIDER_SPEC,
    OpenAireSearchProvider,
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
from souwen.providers.information_sources.stackoverflow import (
    STACKOVERFLOW_PROVIDER_MANIFEST,
    STACKOVERFLOW_PROVIDER_SPEC,
    StackOverflowSearchProvider,
)
from souwen.providers.information_sources.semantic_scholar import (
    SEMANTIC_SCHOLAR_PROVIDER_MANIFEST,
    SEMANTIC_SCHOLAR_PROVIDER_SPEC,
    SemanticScholarSearchProvider,
)
from souwen.providers.information_sources.uspto_odp import (
    USPTO_ODP_BRIDGE_SPEC,
    USPTO_ODP_PROVIDER_MANIFEST,
    UsptoOdpSearchProvider,
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
from souwen.providers.information_sources.zenodo import (
    ZENODO_PROVIDER_MANIFEST,
    ZENODO_PROVIDER_SPEC,
    ZenodoSearchProvider,
)
from souwen.providers.information_sources.datacite import (
    DATACITE_PROVIDER_MANIFEST,
    DATACITE_PROVIDER_SPEC,
    DataCiteSearchProvider,
)
from souwen.providers.information_sources.doab import (
    DOAB_PROVIDER_MANIFEST,
    DOAB_PROVIDER_SPEC,
    DOABSearchProvider,
)
from souwen.providers.information_sources.figshare import (
    FIGSHARE_PROVIDER_MANIFEST,
    FIGSHARE_PROVIDER_SPEC,
    FigshareSearchProvider,
)
from souwen.providers.information_sources.internet_archive import (
    INTERNET_ARCHIVE_PROVIDER_MANIFEST,
    INTERNET_ARCHIVE_PROVIDER_SPEC,
    InternetArchiveSearchProvider,
)
from souwen.providers.information_sources.library_of_congress import (
    LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST,
    LIBRARY_OF_CONGRESS_PROVIDER_SPEC,
    LibraryOfCongressSearchProvider,
)
from souwen.providers.information_sources.open_library import (
    OPEN_LIBRARY_PROVIDER_MANIFEST,
    OPEN_LIBRARY_PROVIDER_SPEC,
    OpenLibrarySearchProvider,
)
from souwen.providers.information_sources.wikisource import (
    WIKISOURCE_PROVIDER_MANIFEST,
    WIKISOURCE_PROVIDER_SPEC,
    WikisourceSearchProvider,
)
from souwen.providers.runtime_clients.research_output.datacite import DataCiteClient
from souwen.providers.runtime_clients.research_output.figshare import FigshareClient
from souwen.providers.runtime_clients.web.baidu import BaiduClient
from souwen.providers.runtime_clients.web.bing import BingClient
from souwen.providers.runtime_clients.web.bing_cn import BingCnClient
from souwen.providers.runtime_clients.web.brave import BraveClient
from souwen.providers.runtime_clients.web.builtin import BuiltinFetcherClient
from souwen.providers.runtime_clients.web.coolapk import CoolapkClient
from souwen.providers.runtime_clients.web.csdn import CSDNClient
from souwen.providers.runtime_clients.web.ddg_images import DuckDuckGoImagesClient
from souwen.providers.runtime_clients.web.ddg_news import DuckDuckGoNewsClient
from souwen.providers.runtime_clients.web.ddg_videos import DuckDuckGoVideosClient
from souwen.providers.runtime_clients.web.duckduckgo import DuckDuckGoClient
from souwen.providers.runtime_clients.web.github import GitHubClient
from souwen.providers.runtime_clients.web.google import GoogleClient
from souwen.providers.runtime_clients.web.hostloc import HostLocClient
from souwen.providers.runtime_clients.web.jina_reader import JinaReaderClient
from souwen.providers.runtime_clients.web.juejin import JuejinClient
from souwen.providers.runtime_clients.web.mojeek import MojeekClient
from souwen.providers.runtime_clients.web.nodeseek import NodeSeekClient
from souwen.providers.runtime_clients.web.searxng import SearXNGClient
from souwen.providers.runtime_clients.web.stackoverflow import StackOverflowClient
from souwen.providers.runtime_clients.web.startpage import StartpageClient
from souwen.providers.runtime_clients.web.v2ex import V2EXClient
from souwen.providers.runtime_clients.web.wayback import WaybackClient
from souwen.providers.runtime_clients.web.wikipedia import WikipediaClient
from souwen.providers.runtime_clients.web.xiaohongshu import XiaohongshuClient
from souwen.providers.runtime_clients.web.yahoo import YahooClient
from souwen.providers.runtime_clients.web.yandex import YandexClient
from souwen.providers.runtime_clients.web.youtube import YouTubeClient
from souwen.worker.browser_fetch.protocol import BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST


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


def _build_reviewed_client_provider(
    provider_type: type[Any],
    client_factory: Callable[[Mapping[str, object], Mapping[str, str]], Any],
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    reviewed_proxy: str | None,
) -> Any:
    """Construct Batch 3 bridges without undeclared existing channel transport overrides."""

    with without_source_channel_overrides(proxy=reviewed_proxy):
        client = client_factory(configuration, secrets)
    return provider_type(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


def _build_reviewed_batch_four_provider(
    provider_type: type[Any],
    client_factory: Callable[[Mapping[str, object], Mapping[str, str], SouWenConfig], Any],
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    reviewed_proxy: str | None,
    config: SouWenConfig,
) -> Any:
    """Construct Batch 4 bridges from the exact runtime config and reviewed network policy."""

    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        client = client_factory(configuration, secrets, config)
    return provider_type(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


_BATCH_FIVE_SEARCH_SOURCE_IDS = (
    "baidu",
    "bing",
    "bing_cn",
    "brave",
    "coolapk",
    "csdn",
    "duckduckgo",
    "duckduckgo_images",
    "duckduckgo_news",
    "duckduckgo_videos",
    "google",
    "hostloc",
    "juejin",
    "mojeek",
    "nodeseek",
    "startpage",
    "v2ex",
    "xiaohongshu",
    "yahoo",
    "yandex",
)
_BATCH_FIVE_DDG_SITE_SOURCE_IDS = frozenset(
    {"coolapk", "hostloc", "nodeseek", "v2ex", "xiaohongshu"}
)
_BATCH_FIVE_CLIENT_TYPES: Mapping[str, type[Any]] = {
    "baidu": BaiduClient,
    "bing": BingClient,
    "bing_cn": BingCnClient,
    "brave": BraveClient,
    "coolapk": CoolapkClient,
    "csdn": CSDNClient,
    "duckduckgo": DuckDuckGoClient,
    "duckduckgo_images": DuckDuckGoImagesClient,
    "duckduckgo_news": DuckDuckGoNewsClient,
    "duckduckgo_videos": DuckDuckGoVideosClient,
    "google": GoogleClient,
    "hostloc": HostLocClient,
    "juejin": JuejinClient,
    "mojeek": MojeekClient,
    "nodeseek": NodeSeekClient,
    "startpage": StartpageClient,
    "v2ex": V2EXClient,
    "xiaohongshu": XiaohongshuClient,
    "yahoo": YahooClient,
    "yandex": YandexClient,
}
_SELF_HOSTED_CLIENT_TYPES: Mapping[str, type[Any]] = {
    "searxng": SearXNGClient,
}
_SELF_HOSTED_CONFIG_FIELDS = {
    "searxng": "searxng_url",
}


def _batch_five_search_binding(
    provider_id: str,
) -> tuple[ProviderManifest, ClientSearchProviderSpec, type[Any], str]:
    module = importlib.import_module(f"souwen.providers.information_sources.{provider_id}")
    manifests = tuple(
        value for value in vars(module).values() if isinstance(value, ProviderManifest)
    )
    specs = tuple(
        value for value in vars(module).values() if isinstance(value, ClientSearchProviderSpec)
    )
    provider_types = tuple(
        value
        for value in vars(module).values()
        if isinstance(value, type)
        and value is not ClientSearchProvider
        and issubclass(value, ClientSearchProvider)
        and value.__module__.startswith(module.__name__)
    )
    if len(manifests) != 1 or len(specs) != 1 or len(provider_types) != 1:
        raise RuntimeError(f"invalid Batch 5 provider package: {provider_id}")
    return manifests[0], specs[0], provider_types[0], provider_id


_BATCH_FIVE_SEARCH_BINDINGS = tuple(
    _batch_five_search_binding(provider_id) for provider_id in _BATCH_FIVE_SEARCH_SOURCE_IDS
)

_BATCH_SIX_SELF_HOSTED_SOURCE_IDS = ("searxng",)


def _batch_six_search_binding(
    provider_id: str,
) -> tuple[ProviderManifest, ClientSearchProviderSpec, type[Any], str]:
    module = importlib.import_module(f"souwen.providers.information_sources.{provider_id}")
    manifests = tuple(
        value for value in vars(module).values() if isinstance(value, ProviderManifest)
    )
    specs = tuple(
        value for value in vars(module).values() if isinstance(value, ClientSearchProviderSpec)
    )
    provider_types = tuple(
        value
        for value in vars(module).values()
        if isinstance(value, type)
        and value is not ClientSearchProvider
        and issubclass(value, ClientSearchProvider)
        and value.__module__.startswith(module.__name__)
    )
    if len(manifests) != 1 or len(specs) != 1 or len(provider_types) != 1:
        raise RuntimeError(f"invalid Batch 6 provider package: {provider_id}")
    return manifests[0], specs[0], provider_types[0], provider_id


_BATCH_SIX_SEARCH_BINDINGS = tuple(
    _batch_six_search_binding(provider_id) for provider_id in _BATCH_SIX_SELF_HOSTED_SOURCE_IDS
)


def _build_reviewed_batch_five_search_provider(
    provider_type: type[Any],
    provider_id: str,
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    reviewed_proxy: str | None,
    config: SouWenConfig,
) -> Any:
    client_type = _BATCH_FIVE_CLIENT_TYPES[provider_id]
    kwargs: dict[str, object] = (
        {}
        if provider_id.startswith("duckduckgo") or provider_id in _BATCH_FIVE_DDG_SITE_SOURCE_IDS
        else {"follow_redirects": False}
    )
    if provider_id == "bilibili":
        kwargs["sessdata"] = secrets.get("BILIBILI_SESSDATA")
    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        client = client_type(**kwargs)
        if provider_id in _BATCH_FIVE_DDG_SITE_SOURCE_IDS:
            client._ddg_client = DuckDuckGoClient()
    return provider_type(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


def _build_reviewed_batch_six_search_provider(
    provider_type: type[Any],
    provider_id: str,
    spec: ClientSearchProviderSpec,
    configuration: Mapping[str, object],
    reviewed_proxy: str | None,
    config: SouWenConfig,
) -> Any:
    resolved_configuration, _ = resolve_provider_inputs(spec, configuration, {})
    client_type = _SELF_HOSTED_CLIENT_TYPES[provider_id]
    source_timeout = config.get_source_config(provider_id).timeout or config.timeout
    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=source_timeout,
        max_retries=config.max_retries,
    ):
        client = client_type(
            instance_url=resolved_configuration["base_url"],
            follow_redirects=False,
        )
    return provider_type(
        _RuntimeClientAdapter(client),
        enabled=bool(resolved_configuration["enabled"]),
    )


def _construct_reviewed_batch_five_fetch_client(
    client_type: type[Any],
    reviewed_proxy: str | None,
    config: SouWenConfig,
) -> Any:
    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        return client_type()


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
_BATCH_TWO_SEARCH_BINDINGS: tuple[
    tuple[
        ProviderManifest,
        ProviderSpec,
        type[Any],
        Callable[[Mapping[str, object], Mapping[str, str]], Any],
    ],
    ...,
] = (
    (
        DOAJ_PROVIDER_MANIFEST,
        DOAJ_PROVIDER_SPEC,
        DoajSearchProvider,
        lambda _configuration, secrets: DoajClient(api_key=secrets.get("DOAJ_API_KEY")),
    ),
    (
        EPO_OPS_PROVIDER_MANIFEST,
        EPO_OPS_BRIDGE_SPEC,
        EpoOpsSearchProvider,
        lambda _configuration, secrets: EpoOpsClient(
            consumer_key=secrets["EPO_CONSUMER_KEY"],
            consumer_secret=secrets["EPO_CONSUMER_SECRET"],
        ),
    ),
    (
        OPENAIRE_PROVIDER_MANIFEST,
        OPENAIRE_PROVIDER_SPEC,
        OpenAireSearchProvider,
        lambda _configuration, secrets: OpenAireClient(api_key=secrets.get("OPENAIRE_API_KEY")),
    ),
    (
        SEMANTIC_SCHOLAR_PROVIDER_MANIFEST,
        SEMANTIC_SCHOLAR_PROVIDER_SPEC,
        SemanticScholarSearchProvider,
        lambda _configuration, secrets: SemanticScholarClient(
            api_key=secrets.get("SEMANTIC_SCHOLAR_API_KEY")
        ),
    ),
    (
        USPTO_ODP_PROVIDER_MANIFEST,
        USPTO_ODP_BRIDGE_SPEC,
        UsptoOdpSearchProvider,
        lambda _configuration, secrets: UsptoOdpClient(api_key=secrets["USPTO_API_KEY"]),
    ),
    (
        ZENODO_PROVIDER_MANIFEST,
        ZENODO_PROVIDER_SPEC,
        ZenodoSearchProvider,
        lambda _configuration, secrets: ZenodoClient(
            access_token=secrets.get("ZENODO_ACCESS_TOKEN")
        ),
    ),
)
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
_BATCH_FOUR_SEARCH_BINDINGS: tuple[
    tuple[
        ProviderManifest,
        ProviderSpec,
        type[Any],
        Callable[[Mapping[str, object], Mapping[str, str], SouWenConfig], Any],
    ],
    ...,
] = (
    (
        DATACITE_PROVIDER_MANIFEST,
        DATACITE_PROVIDER_SPEC,
        DataCiteSearchProvider,
        lambda _configuration, _secrets, _config: DataCiteClient(),
    ),
    (
        DOAB_PROVIDER_MANIFEST,
        DOAB_PROVIDER_SPEC,
        DOABSearchProvider,
        lambda _configuration, _secrets, _config: DOABClient(),
    ),
    (
        FIGSHARE_PROVIDER_MANIFEST,
        FIGSHARE_PROVIDER_SPEC,
        FigshareSearchProvider,
        lambda _configuration, _secrets, _config: FigshareClient(),
    ),
    (
        INTERNET_ARCHIVE_PROVIDER_MANIFEST,
        INTERNET_ARCHIVE_PROVIDER_SPEC,
        InternetArchiveSearchProvider,
        lambda _configuration, _secrets, _config: InternetArchiveClient(),
    ),
    (
        LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST,
        LIBRARY_OF_CONGRESS_PROVIDER_SPEC,
        LibraryOfCongressSearchProvider,
        lambda _configuration, _secrets, _config: LibraryOfCongressClient(),
    ),
    (
        OPEN_LIBRARY_PROVIDER_MANIFEST,
        OPEN_LIBRARY_PROVIDER_SPEC,
        OpenLibrarySearchProvider,
        lambda _configuration, _secrets, _config: OpenLibraryClient(),
    ),
    (
        WIKISOURCE_PROVIDER_MANIFEST,
        WIKISOURCE_PROVIDER_SPEC,
        WikisourceSearchProvider,
        lambda _configuration, _secrets, _config: WikisourceClient(),
    ),
)
_BATCH_TWO_MANIFEST_IDS = frozenset(
    manifest.id for manifest, _spec, _provider_type, _client_factory in _BATCH_TWO_SEARCH_BINDINGS
)
_BATCH_THREE_SEARCH_ONLY_MANIFEST_IDS = frozenset(
    manifest.id
    for manifest, _spec, _provider_type, _client_factory in _BATCH_THREE_SEARCH_ONLY_BINDINGS
)
_BATCH_THREE_MULTI_MANIFEST_IDS = frozenset(
    manifest.id
    for manifest, _search_spec, _fetch_spec, _search_type, _fetch_type, _client_factory in _BATCH_THREE_MULTI_BINDINGS
)
_BATCH_THREE_FETCH_ONLY_MANIFEST_IDS = frozenset(
    manifest.id
    for manifest, _spec, _provider_type, _client_factory in _BATCH_THREE_FETCH_ONLY_BINDINGS
)
_BATCH_THREE_MANIFEST_IDS = (
    _BATCH_THREE_SEARCH_ONLY_MANIFEST_IDS
    | _BATCH_THREE_MULTI_MANIFEST_IDS
    | _BATCH_THREE_FETCH_ONLY_MANIFEST_IDS
)
_BATCH_FOUR_MANIFEST_IDS = frozenset(
    manifest.id for manifest, _spec, _provider_type, _client_factory in _BATCH_FOUR_SEARCH_BINDINGS
)
_BATCH_FIVE_MANIFEST_IDS = frozenset(
    manifest.id for manifest, _spec, _provider_type, _provider_id in _BATCH_FIVE_SEARCH_BINDINGS
)
_BATCH_SIX_MANIFEST_IDS = frozenset(
    manifest.id for manifest, _spec, _provider_type, _provider_id in _BATCH_SIX_SEARCH_BINDINGS
)
_MIGRATED_PROVIDER_IDS = (
    _BATCH_ONE_MANIFEST_IDS
    | _BATCH_TWO_MANIFEST_IDS
    | _BATCH_THREE_MANIFEST_IDS
    | _BATCH_FOUR_MANIFEST_IDS
    | _BATCH_FIVE_MANIFEST_IDS
    | _BATCH_SIX_MANIFEST_IDS
)


def _search_provider_declarations() -> tuple[tuple[ProviderManifest, ProviderSpec], ...]:
    """Return the one reviewed manifest/spec declaration for every Search provider."""

    return (
        (OPENALEX_PROVIDER_MANIFEST, OPENALEX_REST_SPEC),
        (ERIC_PROVIDER_MANIFEST, ERIC_REST_SPEC),
        (PATENTSVIEW_PROVIDER_MANIFEST, PATENTSVIEW_REST_SPEC),
        *((manifest, spec) for manifest, spec, _provider, _factory in _BATCH_ONE_SEARCH_BINDINGS),
        *((manifest, spec) for manifest, spec, _provider, _factory in _BATCH_TWO_SEARCH_BINDINGS),
        *(
            (manifest, spec)
            for manifest, spec, _provider, _factory in _BATCH_THREE_SEARCH_ONLY_BINDINGS
        ),
        *(
            (manifest, search_spec)
            for (
                manifest,
                search_spec,
                _fetch_spec,
                _search_provider,
                _fetch_provider,
                _factory,
            ) in _BATCH_THREE_MULTI_BINDINGS
        ),
        *((manifest, spec) for manifest, spec, _provider, _factory in _BATCH_FOUR_SEARCH_BINDINGS),
        *(
            (manifest, spec)
            for manifest, spec, _provider, _provider_id in _BATCH_FIVE_SEARCH_BINDINGS
        ),
        *(
            (manifest, spec)
            for manifest, spec, _provider, _provider_id in _BATCH_SIX_SEARCH_BINDINGS
        ),
    )


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


def _self_hosted_base_url(config: SouWenConfig, provider_id: str) -> str:
    field = _SELF_HOSTED_CONFIG_FIELDS[provider_id]
    value = config.resolve_base_url(provider_id, getattr(config, field, None) or "")
    return validate_self_hosted_base_url(value)


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
        if manifest.id in _BATCH_SIX_MANIFEST_IDS:
            if not config.is_source_enabled(manifest.id, default=True):
                raise ValueError("provider is disabled")
            return {
                "enabled": True,
                "base_url": _self_hosted_base_url(config, manifest.id),
            }
        if manifest.id in _MIGRATED_PROVIDER_IDS:
            if not config.is_source_enabled(manifest.id, default=True):
                raise ValueError("provider is disabled")
            optional_module = {
                "newspaper": "newspaper",
                "readability": "readability",
            }.get(manifest.id)
            if optional_module is not None and importlib.util.find_spec(optional_module) is None:
                raise ValueError("optional provider runtime is unavailable")
            if manifest.id == "zotero":
                library_id = (config.zotero_library_id or "").strip()
                library_type = (config.zotero_library_type or "user").strip().lower()
                if not library_id or library_type not in {"user", "group"}:
                    raise ValueError("invalid Zotero library configuration")
                return {
                    "enabled": True,
                    "library_id": library_id,
                    "library_type": library_type,
                }
            return {"enabled": True}
        if manifest.id == "builtin-fetch":
            if not config.is_source_enabled("builtin-fetch", default=True):
                raise ValueError("provider is disabled")
            return {"enabled": True}
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
        if manifest.id in (
            _BATCH_TWO_MANIFEST_IDS | _BATCH_THREE_MANIFEST_IDS | _BATCH_FIVE_MANIFEST_IDS
        ):
            resolved: dict[str, str] = {}
            for reference in _references:
                field_name = reference.lower()
                if reference == "BILIBILI_SESSDATA":
                    value = config.bilibili_sessdata
                elif reference.endswith(("_SECRET", "_ACCOUNT_ID")):
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


def _missing_provider_configuration(
    config: SouWenConfig, manifest: ProviderManifest
) -> tuple[str, ...]:
    """Return safe field names only; credential values never leave the resolver."""

    if manifest.id == "patentsview":
        return ("patentsview_api_key",) if not _patentsview_api_key(config) else ()
    if manifest.id in _BATCH_SIX_MANIFEST_IDS:
        try:
            _self_hosted_base_url(config, manifest.id)
        except ValueError:
            return (_SELF_HOSTED_CONFIG_FIELDS[manifest.id],)
        return ()
    if manifest.id not in (_BATCH_TWO_MANIFEST_IDS | _BATCH_THREE_MANIFEST_IDS):
        return ()
    resolved = _secret_resolver(config)(manifest, manifest.secrets.all_references)
    missing = [
        reference.lower() for reference in manifest.secrets.references if reference not in resolved
    ]
    if manifest.id == "zotero":
        if not isinstance(config.zotero_library_id, str) or not config.zotero_library_id.strip():
            missing.append("zotero_library_id")
        library_type = (config.zotero_library_type or "user").strip().lower()
        if library_type not in {"user", "group"}:
            missing.append("zotero_library_type")
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
        elif provider_id in _MIGRATED_PROVIDER_IDS:
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
                    _RuntimeClientAdapter(client_factory(secrets)),
                    enabled=configuration["enabled"],
                )
            ),
            provider_type=provider_type,
        )
    for manifest, _spec, provider_type, client_factory in _BATCH_TWO_SEARCH_BINDINGS:
        validate_spec_manifest(_spec, manifest)
        manager.register_factory(
            package_id=manifest.id,
            export=manifest.adapters[0].export,
            factory=lambda configuration, secrets, provider_type=provider_type, client_factory=client_factory: (
                provider_type(
                    _RuntimeClientAdapter(client_factory(configuration, secrets)),
                    enabled=configuration["enabled"],
                )
            ),
            provider_type=provider_type,
        )
    for manifest, _spec, provider_type, client_factory in _BATCH_THREE_SEARCH_ONLY_BINDINGS:
        validate_spec_manifest(_spec, manifest)
        reviewed_proxy = (
            config.resolve_proxy(manifest.id) if manifest.network.proxy_supported else None
        )
        manager.register_factory(
            package_id=manifest.id,
            export=manifest.adapters[0].export,
            factory=lambda configuration, secrets, provider_type=provider_type, client_factory=client_factory, reviewed_proxy=reviewed_proxy: (
                _build_reviewed_client_provider(
                    provider_type,
                    client_factory,
                    configuration,
                    secrets,
                    reviewed_proxy,
                )
            ),
            provider_type=provider_type,
        )
    for (
        manifest,
        search_spec,
        fetch_spec,
        search_type,
        fetch_type,
        client_factory,
    ) in _BATCH_THREE_MULTI_BINDINGS:
        validate_spec_manifest(search_spec, manifest)
        validate_spec_manifest(fetch_spec, manifest)
        reviewed_proxy = (
            config.resolve_proxy(manifest.id) if manifest.network.proxy_supported else None
        )
        search_export = next(
            adapter.export for adapter in manifest.adapters if adapter.capability == "search"
        )
        fetch_export = next(
            adapter.export for adapter in manifest.adapters if adapter.capability == "fetch"
        )
        manager.register_factory(
            package_id=manifest.id,
            export=search_export,
            factory=lambda configuration, secrets, search_type=search_type, client_factory=client_factory, reviewed_proxy=reviewed_proxy: (
                _build_reviewed_client_provider(
                    search_type,
                    client_factory,
                    configuration,
                    secrets,
                    reviewed_proxy,
                )
            ),
            provider_type=search_type,
        )
        manager.register_factory(
            package_id=manifest.id,
            export=fetch_export,
            factory=lambda configuration, secrets, fetch_type=fetch_type, client_factory=client_factory, reviewed_proxy=reviewed_proxy: (
                _build_reviewed_client_provider(
                    fetch_type,
                    client_factory,
                    configuration,
                    secrets,
                    reviewed_proxy,
                )
            ),
            provider_type=fetch_type,
        )
    for manifest, spec, provider_type, client_factory in _BATCH_THREE_FETCH_ONLY_BINDINGS:
        validate_spec_manifest(spec, manifest)
        reviewed_proxy = (
            config.resolve_proxy(manifest.id) if manifest.network.proxy_supported else None
        )
        manager.register_factory(
            package_id=manifest.id,
            export=manifest.adapters[0].export,
            factory=lambda configuration, secrets, provider_type=provider_type, client_factory=client_factory, reviewed_proxy=reviewed_proxy: (
                _build_reviewed_client_provider(
                    provider_type,
                    client_factory,
                    configuration,
                    secrets,
                    reviewed_proxy,
                )
            ),
            provider_type=provider_type,
        )
    for manifest, spec, provider_type, client_factory in _BATCH_FOUR_SEARCH_BINDINGS:
        validate_spec_manifest(spec, manifest)
        reviewed_proxy = (
            config.resolve_proxy(manifest.id) if manifest.network.proxy_supported else None
        )
        manager.register_factory(
            package_id=manifest.id,
            export=manifest.adapters[0].export,
            factory=lambda configuration, secrets, provider_type=provider_type, client_factory=client_factory, reviewed_proxy=reviewed_proxy: (
                _build_reviewed_batch_four_provider(
                    provider_type,
                    client_factory,
                    configuration,
                    secrets,
                    reviewed_proxy,
                    config,
                )
            ),
            provider_type=provider_type,
        )
    for manifest, spec, provider_type, provider_id in _BATCH_FIVE_SEARCH_BINDINGS:
        validate_spec_manifest(spec, manifest)
        reviewed_proxy = (
            config.resolve_proxy(manifest.id) if manifest.network.proxy_supported else None
        )
        manager.register_factory(
            package_id=manifest.id,
            export=manifest.adapters[0].export,
            factory=lambda configuration, secrets, provider_type=provider_type, provider_id=provider_id, reviewed_proxy=reviewed_proxy: (
                _build_reviewed_batch_five_search_provider(
                    provider_type,
                    provider_id,
                    configuration,
                    secrets,
                    reviewed_proxy,
                    config,
                )
            ),
            provider_type=provider_type,
        )
    for manifest, spec, provider_type, provider_id in _BATCH_SIX_SEARCH_BINDINGS:
        validate_spec_manifest(spec, manifest)
        reviewed_proxy = (
            config.resolve_proxy(manifest.id) if manifest.network.proxy_supported else None
        )
        manager.register_factory(
            package_id=manifest.id,
            export=manifest.adapters[0].export,
            factory=lambda configuration, _secrets, provider_type=provider_type, provider_id=provider_id, spec=spec, reviewed_proxy=reviewed_proxy: (
                _build_reviewed_batch_six_search_provider(
                    provider_type,
                    provider_id,
                    spec,
                    configuration,
                    reviewed_proxy,
                    config,
                )
            ),
            provider_type=provider_type,
        )
    manager.register_factory(
        package_id=ARXIV_FULLTEXT_PROVIDER_MANIFEST.id,
        export="ArxivFulltextFetchProvider",
        factory=lambda configuration, _secrets: ArxivFulltextFetchProvider(
            _RuntimeClientAdapter(ArxivFulltextClient()),
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
    manager.discover(
        (
            OPENALEX_PROVIDER_MANIFEST,
            ERIC_PROVIDER_MANIFEST,
            PATENTSVIEW_PROVIDER_MANIFEST,
            *(
                manifest
                for manifest, _spec, _provider_type, _client_factory in _BATCH_ONE_SEARCH_BINDINGS
            ),
            *(
                manifest
                for manifest, _spec, _provider_type, _client_factory in _BATCH_TWO_SEARCH_BINDINGS
            ),
            *(
                manifest
                for manifest, _spec, _provider_type, _client_factory in _BATCH_THREE_SEARCH_ONLY_BINDINGS
            ),
            *(
                manifest
                for (
                    manifest,
                    _search_spec,
                    _fetch_spec,
                    _search_type,
                    _fetch_type,
                    _client_factory,
                ) in _BATCH_THREE_MULTI_BINDINGS
            ),
            *(
                manifest
                for manifest, _spec, _provider_type, _client_factory in _BATCH_THREE_FETCH_ONLY_BINDINGS
            ),
            *(
                manifest
                for manifest, _spec, _provider_type, _client_factory in _BATCH_FOUR_SEARCH_BINDINGS
            ),
            *(
                manifest
                for manifest, _spec, _provider_type, _provider_id in _BATCH_FIVE_SEARCH_BINDINGS
            ),
            *(
                manifest
                for manifest, _spec, _provider_type, _provider_id in _BATCH_SIX_SEARCH_BINDINGS
            ),
            ARXIV_FULLTEXT_PROVIDER_MANIFEST,
            BUILTIN_FETCH_MANIFEST,
        )
    )

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
    fetch = FetchModuleService(
        manager,
        provider_adapter_ids={
            "arxiv_fulltext": "arxiv_fulltext-fetch",
            "newspaper": "newspaper-fetch",
            "readability": "readability-fetch",
            **{
                manifest.id: next(
                    adapter.id for adapter in manifest.adapters if adapter.capability == "fetch"
                )
                for (
                    manifest,
                    _search_spec,
                    _fetch_spec,
                    _search_type,
                    _fetch_type,
                    _client_factory,
                ) in _BATCH_THREE_MULTI_BINDINGS
            },
            **{
                manifest.id: manifest.adapters[0].id
                for manifest, _spec, _provider_type, _client_factory in _BATCH_THREE_FETCH_ONLY_BINDINGS
            },
        },
        browser_executor=browser_client,
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
