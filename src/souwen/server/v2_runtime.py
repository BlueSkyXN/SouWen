"""Composition root for the P4 target vertical slice."""

from __future__ import annotations

import inspect
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from souwen import __version__
from souwen.book.doab import DOABClient
from souwen.book.internet_archive import InternetArchiveClient
from souwen.book.library_of_congress import LibraryOfCongressClient
from souwen.book.librivox import LibriVoxClient
from souwen.book.oapen import OAPENClient
from souwen.book.open_library import OpenLibraryClient
from souwen.book.wikisource import WikisourceClient
from souwen.common_runtime.observability import get_request_id, get_source_sha
from souwen.common_runtime.transport import HttpTransport
from souwen.config import SouWenConfig
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
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
from souwen.local_catalog.gutenberg import (
    GutenbergLocalCatalogClient,
    gutenberg_catalog_ready,
)
from souwen.local_catalog.taiwan_new_books import (
    TaiwanNewBooksLocalCatalogClient,
    taiwan_new_books_catalog_ready,
)
from souwen.paper.eric import EricClient
from souwen.paper.arxiv import ArxivClient
from souwen.paper.arxiv_fulltext import ArxivFulltextClient
from souwen.paper.biorxiv import BioRxivClient
from souwen.paper.crossref import CrossrefClient
from souwen.paper.dblp import DblpClient
from souwen.paper.europepmc import EuropePmcClient
from souwen.paper.core import CoreClient
from souwen.paper.doaj import DoajClient
from souwen.paper.hal import HalClient
from souwen.paper.huggingface import HuggingFaceClient
from souwen.paper.iacr import IacrClient
from souwen.paper.ieee_xplore import IeeeXploreClient
from souwen.paper.openalex import OpenAlexClient
from souwen.paper.openaire import OpenAireClient
from souwen.paper.osti import OstiClient
from souwen.paper.pmc import PmcClient
from souwen.paper.pubmed import PubMedClient
from souwen.paper.semantic_scholar import SemanticScholarClient
from souwen.paper.zenodo import ZenodoClient
from souwen.paper.zotero import ZoteroClient
from souwen.patent.cnipa import CnipaClient
from souwen.patent.epo_ops import EpoOpsClient
from souwen.patent.google_patents_scraper import GooglePatentsScraper
from souwen.patent.patsnap import PatSnapClient
from souwen.patent.patentsview import PatentsViewClient
from souwen.patent.pqai import PqaiClient
from souwen.patent.the_lens import TheLensClient
from souwen.patent.uspto_odp import UsptoOdpClient
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
from souwen.providers.fetch_sources.apify import (
    APIFY_FETCH_PROFILE,
    APIFY_PROVIDER_MANIFEST,
    ApifyFetchProvider,
)
from souwen.providers.fetch_sources.builtin import BUILTIN_FETCH_MANIFEST, BuiltinFetchProvider
from souwen.providers.fetch_sources.cloudflare import (
    CLOUDFLARE_FETCH_PROFILE,
    CLOUDFLARE_PROVIDER_MANIFEST,
    CloudflareFetchProvider,
)
from souwen.providers.fetch_sources.deepwiki import (
    DEEPWIKI_FETCH_PROFILE,
    DEEPWIKI_PROVIDER_MANIFEST,
    DeepWikiFetchProvider,
)
from souwen.providers.fetch_sources.diffbot import (
    DIFFBOT_FETCH_PROFILE,
    DIFFBOT_PROVIDER_MANIFEST,
    DiffbotFetchProvider,
)
from souwen.providers.fetch_sources.jina_reader import (
    JINA_READER_FETCH_PROFILE,
    JINA_READER_PROVIDER_MANIFEST,
    JinaReaderFetchProvider,
)
from souwen.providers.fetch_sources.scraperapi import (
    SCRAPERAPI_FETCH_PROFILE,
    SCRAPERAPI_PROVIDER_MANIFEST,
    ScraperAPIFetchProvider,
)
from souwen.providers.fetch_sources.scrapfly import (
    SCRAPFLY_FETCH_PROFILE,
    SCRAPFLY_PROVIDER_MANIFEST,
    ScrapflyFetchProvider,
)
from souwen.providers.fetch_sources.scrapingbee import (
    SCRAPINGBEE_FETCH_PROFILE,
    SCRAPINGBEE_PROVIDER_MANIFEST,
    ScrapingBeeFetchProvider,
)
from souwen.providers.fetch_sources.wayback import (
    WAYBACK_FETCH_PROVIDER_SPEC,
    WAYBACK_PROVIDER_MANIFEST,
    WaybackFetchProvider,
)
from souwen.providers.fetch_sources.zenrows import (
    ZENROWS_FETCH_PROFILE,
    ZENROWS_PROVIDER_MANIFEST,
    ZenRowsFetchProvider,
)
from souwen.providers.information_sources.aliyun_iqs import (
    ALIYUN_IQS_PROVIDER_MANIFEST,
    ALIYUN_IQS_PROVIDER_SPEC,
    AliyunIQSSearchProvider,
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
from souwen.providers.information_sources.brave_api import (
    BRAVE_API_PROVIDER_MANIFEST,
    BRAVE_API_PROVIDER_SPEC,
    BraveApiSearchProvider,
)
from souwen.providers.information_sources.crossref import (
    CROSSREF_PROVIDER_MANIFEST,
    CROSSREF_PROVIDER_SPEC,
    CrossrefSearchProvider,
)
from souwen.providers.information_sources.cnipa import (
    CNIPA_BRIDGE_SPEC,
    CNIPA_PROVIDER_MANIFEST,
    CnipaSearchProvider,
)
from souwen.providers.information_sources.core import (
    CORE_PROVIDER_MANIFEST,
    CORE_PROVIDER_SPEC,
    CoreSearchProvider,
)
from souwen.providers.information_sources.doaj import (
    DOAJ_PROVIDER_MANIFEST,
    DOAJ_PROVIDER_SPEC,
    DoajSearchProvider,
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
from souwen.providers.information_sources.epo_ops import (
    EPO_OPS_BRIDGE_SPEC,
    EPO_OPS_PROVIDER_MANIFEST,
    EpoOpsSearchProvider,
)
from souwen.providers.information_sources.exa import (
    EXA_FETCH_PROVIDER_SPEC,
    EXA_PROVIDER_MANIFEST,
    EXA_SEARCH_PROVIDER_SPEC,
    ExaFetchProvider,
    ExaSearchProvider,
)
from souwen.providers.information_sources.facebook import (
    FACEBOOK_PROVIDER_MANIFEST,
    FACEBOOK_PROVIDER_SPEC,
    FacebookSearchProvider,
)
from souwen.providers.information_sources.feishu_drive import (
    FEISHU_DRIVE_PROVIDER_MANIFEST,
    FEISHU_DRIVE_PROVIDER_SPEC,
    FeishuDriveSearchProvider,
)
from souwen.providers.information_sources.firecrawl import (
    FIRECRAWL_FETCH_PROVIDER_SPEC,
    FIRECRAWL_PROVIDER_MANIFEST,
    FIRECRAWL_SEARCH_PROVIDER_SPEC,
    FirecrawlFetchProvider,
    FirecrawlSearchProvider,
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
from souwen.providers.information_sources.ieee_xplore import (
    IEEE_XPLORE_PROVIDER_MANIFEST,
    IEEE_XPLORE_PROVIDER_SPEC,
    IeeeXploreSearchProvider,
)
from souwen.providers.information_sources.kimi_code import (
    KIMI_CODE_FETCH_PROVIDER_SPEC,
    KIMI_CODE_PROVIDER_MANIFEST,
    KIMI_CODE_SEARCH_PROVIDER_SPEC,
    KimiCodeFetchProvider,
    KimiCodeSearchProvider,
)
from souwen.providers.information_sources.linkup import (
    LINKUP_PROVIDER_MANIFEST,
    LINKUP_PROVIDER_SPEC,
    LinkupSearchProvider,
)
from souwen.providers.information_sources.linuxdo import (
    LINUXDO_PROVIDER_MANIFEST,
    LINUXDO_PROVIDER_SPEC,
    LinuxDoSearchProvider,
)
from souwen.providers.information_sources.metaso import (
    METASO_FETCH_PROVIDER_SPEC,
    METASO_PROVIDER_MANIFEST,
    METASO_SEARCH_PROVIDER_SPEC,
    MetasoFetchProvider,
    MetasoSearchProvider,
)
from souwen.providers.information_sources.openalex import (
    OPENALEX_PROVIDER_MANIFEST,
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
from souwen.providers.information_sources.patsnap import (
    PATSNAP_BRIDGE_SPEC,
    PATSNAP_PROVIDER_MANIFEST,
    PatSnapSearchProvider,
)
from souwen.providers.information_sources.perplexity import (
    PERPLEXITY_PROVIDER_MANIFEST,
    PERPLEXITY_PROVIDER_SPEC,
    PerplexitySearchProvider,
)
from souwen.providers.information_sources.pqai import (
    PQAI_BRIDGE_SPEC,
    PQAI_PROVIDER_MANIFEST,
    PqaiSearchProvider,
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
from souwen.providers.information_sources.reddit import (
    REDDIT_PROVIDER_MANIFEST,
    REDDIT_PROVIDER_SPEC,
    RedditSearchProvider,
)
from souwen.providers.information_sources.scrapingdog import (
    SCRAPINGDOG_PROVIDER_MANIFEST,
    SCRAPINGDOG_PROVIDER_SPEC,
    ScrapingDogSearchProvider,
)
from souwen.providers.information_sources.serpapi import (
    SERPAPI_PROVIDER_MANIFEST,
    SERPAPI_PROVIDER_SPEC,
    SerpApiSearchProvider,
)
from souwen.providers.information_sources.serper import (
    SERPER_PROVIDER_MANIFEST,
    SERPER_PROVIDER_SPEC,
    SerperSearchProvider,
)
from souwen.providers.information_sources.stackoverflow import (
    STACKOVERFLOW_PROVIDER_MANIFEST,
    STACKOVERFLOW_PROVIDER_SPEC,
    StackOverflowSearchProvider,
)
from souwen.providers.information_sources.tavily import (
    TAVILY_FETCH_PROVIDER_SPEC,
    TAVILY_PROVIDER_MANIFEST,
    TAVILY_SEARCH_PROVIDER_SPEC,
    TavilyFetchProvider,
    TavilySearchProvider,
)
from souwen.providers.information_sources.semantic_scholar import (
    SEMANTIC_SCHOLAR_PROVIDER_MANIFEST,
    SEMANTIC_SCHOLAR_PROVIDER_SPEC,
    SemanticScholarSearchProvider,
)
from souwen.providers.information_sources.the_lens import (
    THE_LENS_BRIDGE_SPEC,
    THE_LENS_PROVIDER_MANIFEST,
    TheLensSearchProvider,
)
from souwen.providers.information_sources.twitter import (
    TWITTER_PROVIDER_MANIFEST,
    TWITTER_PROVIDER_SPEC,
    TwitterSearchProvider,
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
from souwen.providers.information_sources.xcrawl import (
    XCRAWL_FETCH_PROVIDER_SPEC,
    XCRAWL_PROVIDER_MANIFEST,
    XCRAWL_SEARCH_PROVIDER_SPEC,
    XCrawlFetchProvider,
    XCrawlSearchProvider,
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
from souwen.providers.information_sources.zotero import (
    ZOTERO_PROVIDER_MANIFEST,
    ZOTERO_PROVIDER_SPEC,
    ZoteroSearchProvider,
)
from souwen.providers.information_sources.zhipuai import (
    ZHIPUAI_PROVIDER_MANIFEST,
    ZHIPUAI_PROVIDER_SPEC,
    ZhipuAISearchSearchProvider,
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
from souwen.providers.information_sources.gutenberg import (
    GUTENBERG_PROVIDER_MANIFEST,
    GUTENBERG_PROVIDER_SPEC,
    GutenbergSearchProvider,
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
from souwen.providers.information_sources.librivox import (
    LIBRIVOX_PROVIDER_MANIFEST,
    LIBRIVOX_PROVIDER_SPEC,
    LibriVoxSearchProvider,
)
from souwen.providers.information_sources.oapen import (
    OAPEN_PROVIDER_MANIFEST,
    OAPEN_PROVIDER_SPEC,
    OAPENSearchProvider,
)
from souwen.providers.information_sources.open_library import (
    OPEN_LIBRARY_PROVIDER_MANIFEST,
    OPEN_LIBRARY_PROVIDER_SPEC,
    OpenLibrarySearchProvider,
)
from souwen.providers.information_sources.taiwan_new_books import (
    TAIWAN_NEW_BOOKS_PROVIDER_MANIFEST,
    TAIWAN_NEW_BOOKS_PROVIDER_SPEC,
    TaiwanNewBooksSearchProvider,
)
from souwen.providers.information_sources.wikisource import (
    WIKISOURCE_PROVIDER_MANIFEST,
    WIKISOURCE_PROVIDER_SPEC,
    WikisourceSearchProvider,
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
from souwen.registry import defaults_for, get as get_legacy_adapter
from souwen.research_output.datacite import DataCiteClient
from souwen.research_output.figshare import FigshareClient
from souwen.web.apify import ApifyClient
from souwen.web.aliyun_iqs import AliyunIQSClient
from souwen.web.brave_api import BraveApiClient
from souwen.web.builtin import BuiltinFetcherClient
from souwen.web.cloudflare_browser import CloudflareBrowserClient
from souwen.web.deepwiki import DeepWikiClient
from souwen.web.diffbot import DiffbotClient
from souwen.web.exa import ExaClient
from souwen.web.facebook import FacebookClient
from souwen.web.feishu_drive import FeishuDriveClient
from souwen.web.firecrawl import FirecrawlClient
from souwen.web.github import GitHubClient
from souwen.web.jina_reader import JinaReaderClient
from souwen.web.kimi_code import KimiCodeClient
from souwen.web.linkup import LinkupClient
from souwen.web.linuxdo import LinuxDoClient
from souwen.web.metaso import MetasoClient
from souwen.web.perplexity import PerplexityClient
from souwen.web.reddit import RedditClient
from souwen.web.scraperapi import ScraperAPIClient
from souwen.web.scrapfly import ScrapflyClient
from souwen.web.scrapingbee import ScrapingBeeClient
from souwen.web.scrapingdog import ScrapingDogClient
from souwen.web.serpapi import SerpApiClient
from souwen.web.serper import SerperClient
from souwen.web.stackoverflow import StackOverflowClient
from souwen.web.tavily import TavilyClient
from souwen.web.twitter import TwitterClient
from souwen.web.wayback import WaybackClient
from souwen.web.wikipedia import WikipediaClient
from souwen.web.xcrawl import XCrawlClient
from souwen.web.youtube import YouTubeClient
from souwen.web.zenrows import ZenRowsClient
from souwen.web.zhipuai_search import ZhipuAISearchClient
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


def _build_reviewed_legacy_provider(
    provider_type: type[Any],
    client_factory: Callable[[Mapping[str, object], Mapping[str, str]], Any],
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    reviewed_proxy: str | None,
) -> Any:
    """Construct Batch 3 bridges without undeclared legacy channel transport overrides."""

    with without_source_channel_overrides(proxy=reviewed_proxy):
        client = client_factory(configuration, secrets)
    return provider_type(
        _LegacyRuntimeClient(client),
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
        _LegacyRuntimeClient(client),
        enabled=bool(configuration["enabled"]),
    )


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
        CNIPA_PROVIDER_MANIFEST,
        CNIPA_BRIDGE_SPEC,
        CnipaSearchProvider,
        lambda _configuration, secrets: CnipaClient(
            client_id=secrets["CNIPA_CLIENT_ID"],
            client_secret=secrets["CNIPA_CLIENT_SECRET"],
        ),
    ),
    (
        CORE_PROVIDER_MANIFEST,
        CORE_PROVIDER_SPEC,
        CoreSearchProvider,
        lambda _configuration, secrets: CoreClient(api_key=secrets["CORE_API_KEY"]),
    ),
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
        IEEE_XPLORE_PROVIDER_MANIFEST,
        IEEE_XPLORE_PROVIDER_SPEC,
        IeeeXploreSearchProvider,
        lambda _configuration, secrets: IeeeXploreClient(api_key=secrets["IEEE_API_KEY"]),
    ),
    (
        OPENAIRE_PROVIDER_MANIFEST,
        OPENAIRE_PROVIDER_SPEC,
        OpenAireSearchProvider,
        lambda _configuration, secrets: OpenAireClient(api_key=secrets.get("OPENAIRE_API_KEY")),
    ),
    (
        PATSNAP_PROVIDER_MANIFEST,
        PATSNAP_BRIDGE_SPEC,
        PatSnapSearchProvider,
        lambda _configuration, secrets: PatSnapClient(api_key=secrets["PATSNAP_API_KEY"]),
    ),
    (
        PQAI_PROVIDER_MANIFEST,
        PQAI_BRIDGE_SPEC,
        PqaiSearchProvider,
        lambda _configuration, secrets: PqaiClient(api_token=secrets["PQAI_API_TOKEN"]),
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
        THE_LENS_PROVIDER_MANIFEST,
        THE_LENS_BRIDGE_SPEC,
        TheLensSearchProvider,
        lambda _configuration, secrets: TheLensClient(api_token=secrets["LENS_API_TOKEN"]),
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
    (
        ZOTERO_PROVIDER_MANIFEST,
        ZOTERO_PROVIDER_SPEC,
        ZoteroSearchProvider,
        lambda configuration, secrets: ZoteroClient(
            api_key=secrets["ZOTERO_API_KEY"],
            library_id=str(configuration["library_id"]),
            library_type=str(configuration["library_type"]),
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
        ALIYUN_IQS_PROVIDER_MANIFEST,
        ALIYUN_IQS_PROVIDER_SPEC,
        AliyunIQSSearchProvider,
        lambda _configuration, secrets: AliyunIQSClient(api_key=secrets["ALIYUN_IQS_API_KEY"]),
    ),
    (
        BRAVE_API_PROVIDER_MANIFEST,
        BRAVE_API_PROVIDER_SPEC,
        BraveApiSearchProvider,
        lambda _configuration, secrets: BraveApiClient(api_key=secrets["BRAVE_API_KEY"]),
    ),
    (
        FACEBOOK_PROVIDER_MANIFEST,
        FACEBOOK_PROVIDER_SPEC,
        FacebookSearchProvider,
        lambda _configuration, secrets: FacebookClient(
            app_id=secrets["FACEBOOK_APP_ID"],
            app_secret=secrets["FACEBOOK_APP_SECRET"],
        ),
    ),
    (
        FEISHU_DRIVE_PROVIDER_MANIFEST,
        FEISHU_DRIVE_PROVIDER_SPEC,
        FeishuDriveSearchProvider,
        lambda _configuration, secrets: FeishuDriveClient(
            app_id=secrets["FEISHU_APP_ID"],
            app_secret=secrets["FEISHU_APP_SECRET"],
        ),
    ),
    (
        GITHUB_PROVIDER_MANIFEST,
        GITHUB_PROVIDER_SPEC,
        GitHubSearchProvider,
        lambda _configuration, secrets: GitHubClient(token=secrets.get("GITHUB_TOKEN", "")),
    ),
    (
        LINKUP_PROVIDER_MANIFEST,
        LINKUP_PROVIDER_SPEC,
        LinkupSearchProvider,
        lambda _configuration, secrets: LinkupClient(api_key=secrets["LINKUP_API_KEY"]),
    ),
    (
        LINUXDO_PROVIDER_MANIFEST,
        LINUXDO_PROVIDER_SPEC,
        LinuxDoSearchProvider,
        lambda _configuration, _secrets: LinuxDoClient(),
    ),
    (
        PERPLEXITY_PROVIDER_MANIFEST,
        PERPLEXITY_PROVIDER_SPEC,
        PerplexitySearchProvider,
        lambda _configuration, secrets: PerplexityClient(api_key=secrets["PERPLEXITY_API_KEY"]),
    ),
    (
        REDDIT_PROVIDER_MANIFEST,
        REDDIT_PROVIDER_SPEC,
        RedditSearchProvider,
        lambda _configuration, secrets: RedditClient(
            client_id=secrets.get("REDDIT_CLIENT_ID", ""),
            client_secret=secrets.get("REDDIT_CLIENT_SECRET", ""),
        ),
    ),
    (
        SCRAPINGDOG_PROVIDER_MANIFEST,
        SCRAPINGDOG_PROVIDER_SPEC,
        ScrapingDogSearchProvider,
        lambda _configuration, secrets: ScrapingDogClient(api_key=secrets["SCRAPINGDOG_API_KEY"]),
    ),
    (
        SERPAPI_PROVIDER_MANIFEST,
        SERPAPI_PROVIDER_SPEC,
        SerpApiSearchProvider,
        lambda _configuration, secrets: SerpApiClient(api_key=secrets["SERPAPI_API_KEY"]),
    ),
    (
        SERPER_PROVIDER_MANIFEST,
        SERPER_PROVIDER_SPEC,
        SerperSearchProvider,
        lambda _configuration, secrets: SerperClient(api_key=secrets["SERPER_API_KEY"]),
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
        TWITTER_PROVIDER_MANIFEST,
        TWITTER_PROVIDER_SPEC,
        TwitterSearchProvider,
        lambda _configuration, secrets: TwitterClient(bearer_token=secrets["TWITTER_BEARER_TOKEN"]),
    ),
    (
        WIKIPEDIA_PROVIDER_MANIFEST,
        WIKIPEDIA_PROVIDER_SPEC,
        WikipediaSearchProvider,
        lambda _configuration, _secrets: WikipediaClient(),
    ),
    (
        ZHIPUAI_PROVIDER_MANIFEST,
        ZHIPUAI_PROVIDER_SPEC,
        ZhipuAISearchSearchProvider,
        lambda _configuration, secrets: ZhipuAISearchClient(api_key=secrets["ZHIPUAI_API_KEY"]),
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
] = (
    (
        EXA_PROVIDER_MANIFEST,
        EXA_SEARCH_PROVIDER_SPEC,
        EXA_FETCH_PROVIDER_SPEC,
        ExaSearchProvider,
        ExaFetchProvider,
        lambda _configuration, secrets: ExaClient(api_key=secrets["EXA_API_KEY"]),
    ),
    (
        FIRECRAWL_PROVIDER_MANIFEST,
        FIRECRAWL_SEARCH_PROVIDER_SPEC,
        FIRECRAWL_FETCH_PROVIDER_SPEC,
        FirecrawlSearchProvider,
        FirecrawlFetchProvider,
        lambda _configuration, secrets: FirecrawlClient(api_key=secrets["FIRECRAWL_API_KEY"]),
    ),
    (
        KIMI_CODE_PROVIDER_MANIFEST,
        KIMI_CODE_SEARCH_PROVIDER_SPEC,
        KIMI_CODE_FETCH_PROVIDER_SPEC,
        KimiCodeSearchProvider,
        KimiCodeFetchProvider,
        lambda _configuration, secrets: KimiCodeClient(api_key=secrets["KIMI_CODE_API_KEY"]),
    ),
    (
        METASO_PROVIDER_MANIFEST,
        METASO_SEARCH_PROVIDER_SPEC,
        METASO_FETCH_PROVIDER_SPEC,
        MetasoSearchProvider,
        MetasoFetchProvider,
        lambda _configuration, secrets: MetasoClient(api_key=secrets["METASO_API_KEY"]),
    ),
    (
        TAVILY_PROVIDER_MANIFEST,
        TAVILY_SEARCH_PROVIDER_SPEC,
        TAVILY_FETCH_PROVIDER_SPEC,
        TavilySearchProvider,
        TavilyFetchProvider,
        lambda _configuration, secrets: TavilyClient(api_key=secrets["TAVILY_API_KEY"]),
    ),
    (
        XCRAWL_PROVIDER_MANIFEST,
        XCRAWL_SEARCH_PROVIDER_SPEC,
        XCRAWL_FETCH_PROVIDER_SPEC,
        XCrawlSearchProvider,
        XCrawlFetchProvider,
        lambda _configuration, secrets: XCrawlClient(api_key=secrets["XCRAWL_API_KEY"]),
    ),
)

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
        APIFY_PROVIDER_MANIFEST,
        APIFY_FETCH_PROFILE,
        ApifyFetchProvider,
        lambda _configuration, secrets: ApifyClient(api_token=secrets["APIFY_API_TOKEN"]),
    ),
    (
        CLOUDFLARE_PROVIDER_MANIFEST,
        CLOUDFLARE_FETCH_PROFILE,
        CloudflareFetchProvider,
        lambda _configuration, secrets: CloudflareBrowserClient(
            api_token=secrets["CLOUDFLARE_API_TOKEN"],
            account_id=secrets["CLOUDFLARE_ACCOUNT_ID"],
        ),
    ),
    (
        DEEPWIKI_PROVIDER_MANIFEST,
        DEEPWIKI_FETCH_PROFILE,
        DeepWikiFetchProvider,
        lambda _configuration, secrets: DeepWikiClient(
            github_token="",
            jina_api_key=secrets.get("JINA_API_KEY", ""),
        ),
    ),
    (
        DIFFBOT_PROVIDER_MANIFEST,
        DIFFBOT_FETCH_PROFILE,
        DiffbotFetchProvider,
        lambda _configuration, secrets: DiffbotClient(api_token=secrets["DIFFBOT_API_TOKEN"]),
    ),
    (
        JINA_READER_PROVIDER_MANIFEST,
        JINA_READER_FETCH_PROFILE,
        JinaReaderFetchProvider,
        lambda _configuration, secrets: JinaReaderClient(api_key=secrets.get("JINA_API_KEY")),
    ),
    (
        SCRAPERAPI_PROVIDER_MANIFEST,
        SCRAPERAPI_FETCH_PROFILE,
        ScraperAPIFetchProvider,
        lambda _configuration, secrets: ScraperAPIClient(api_key=secrets["SCRAPERAPI_API_KEY"]),
    ),
    (
        SCRAPFLY_PROVIDER_MANIFEST,
        SCRAPFLY_FETCH_PROFILE,
        ScrapflyFetchProvider,
        lambda _configuration, secrets: ScrapflyClient(api_key=secrets["SCRAPFLY_API_KEY"]),
    ),
    (
        SCRAPINGBEE_PROVIDER_MANIFEST,
        SCRAPINGBEE_FETCH_PROFILE,
        ScrapingBeeFetchProvider,
        lambda _configuration, secrets: ScrapingBeeClient(api_key=secrets["SCRAPINGBEE_API_KEY"]),
    ),
    (
        WAYBACK_PROVIDER_MANIFEST,
        WAYBACK_FETCH_PROVIDER_SPEC,
        WaybackFetchProvider,
        lambda _configuration, _secrets: WaybackClient(),
    ),
    (
        ZENROWS_PROVIDER_MANIFEST,
        ZENROWS_FETCH_PROFILE,
        ZenRowsFetchProvider,
        lambda _configuration, secrets: ZenRowsClient(api_key=secrets["ZENROWS_API_KEY"]),
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
        GUTENBERG_PROVIDER_MANIFEST,
        GUTENBERG_PROVIDER_SPEC,
        GutenbergSearchProvider,
        lambda _configuration, _secrets, config: GutenbergLocalCatalogClient(
            config.local_catalog_db_path
        ),
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
        LIBRIVOX_PROVIDER_MANIFEST,
        LIBRIVOX_PROVIDER_SPEC,
        LibriVoxSearchProvider,
        lambda _configuration, _secrets, _config: LibriVoxClient(),
    ),
    (
        OAPEN_PROVIDER_MANIFEST,
        OAPEN_PROVIDER_SPEC,
        OAPENSearchProvider,
        lambda _configuration, _secrets, _config: OAPENClient(),
    ),
    (
        OPEN_LIBRARY_PROVIDER_MANIFEST,
        OPEN_LIBRARY_PROVIDER_SPEC,
        OpenLibrarySearchProvider,
        lambda _configuration, _secrets, _config: OpenLibraryClient(),
    ),
    (
        TAIWAN_NEW_BOOKS_PROVIDER_MANIFEST,
        TAIWAN_NEW_BOOKS_PROVIDER_SPEC,
        TaiwanNewBooksSearchProvider,
        lambda _configuration, _secrets, config: TaiwanNewBooksLocalCatalogClient(
            config.local_catalog_db_path
        ),
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
_MIGRATED_LEGACY_MANIFEST_IDS = (
    _BATCH_ONE_MANIFEST_IDS
    | _BATCH_TWO_MANIFEST_IDS
    | _BATCH_THREE_MANIFEST_IDS
    | _BATCH_FOUR_MANIFEST_IDS
)
_LEGACY_DEFAULT_PROVIDER_IDS = frozenset(
    {
        *defaults_for("paper", "search"),
        *defaults_for("patent", "search"),
        *defaults_for("book", "search"),
        *defaults_for("research_output", "search"),
        *defaults_for("fetch", "fetch"),
    }
)


def _legacy_runtime_default_enabled(provider_id: str) -> bool:
    """Keep runtime eligibility distinct from default Search fan-out selection."""

    return get_legacy_adapter(provider_id).runtime_default_enabled


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
        if manifest.id in _MIGRATED_LEGACY_MANIFEST_IDS:
            if not config.is_source_enabled(
                manifest.id, default=_legacy_runtime_default_enabled(manifest.id)
            ):
                raise ValueError("provider is disabled")
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
            if manifest.id == "gutenberg" and not gutenberg_catalog_ready(
                config.local_catalog_db_path
            ):
                raise ValueError("local catalog unavailable")
            if manifest.id == "taiwan_new_books" and not taiwan_new_books_catalog_ready(
                config.local_catalog_db_path
            ):
                raise ValueError("local catalog unavailable")
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
        if manifest.id in (_BATCH_TWO_MANIFEST_IDS | _BATCH_THREE_MANIFEST_IDS):
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


def _missing_provider_configuration(
    config: SouWenConfig, manifest: ProviderManifest
) -> tuple[str, ...]:
    """Return safe field names only; credential values never leave the resolver."""

    if manifest.id == "patentsview":
        return ("patentsview_api_key",) if not _patentsview_api_key(config) else ()
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
    enabled_llm = set(config.enabled_uniapi_ark_source_ids())
    missing_gateway = config.missing_uniapi_gateway_fields()
    patentsview_enabled = config.is_source_enabled("patentsview", default=False)
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
        elif provider_id in _MIGRATED_LEGACY_MANIFEST_IDS:
            enabled = config.is_source_enabled(
                provider_id, default=_legacy_runtime_default_enabled(provider_id)
            )
        else:
            enabled = config.is_source_enabled(provider_id, default=True)
        if enabled and capability == "llm_search" and missing_gateway:
            missing_fields = missing_gateway
        elif enabled:
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
                    _LegacyRuntimeClient(client_factory(secrets)),
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
                    _LegacyRuntimeClient(client_factory(configuration, secrets)),
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
                _build_reviewed_legacy_provider(
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
                _build_reviewed_legacy_provider(
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
                _build_reviewed_legacy_provider(
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
                _build_reviewed_legacy_provider(
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
                                for binding in _BATCH_TWO_SEARCH_BINDINGS
                                if binding[1].domain == "paper"
                            ),
                            start=100,
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
                            for binding in (
                                *_BATCH_ONE_SEARCH_BINDINGS,
                                *_BATCH_TWO_SEARCH_BINDINGS,
                            )
                            if binding[1].domain == "patent"
                        ),
                        start=1,
                    )
                ),
                **{
                    domain: tuple(
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
                                for binding in _BATCH_FOUR_SEARCH_BINDINGS
                                if binding[1].domain == domain
                                and binding[0].id in _LEGACY_DEFAULT_PROVIDER_IDS
                            ),
                            start=1,
                        )
                    )
                    for domain in ("book", "research_output")
                },
            },
            explicit_selections=(
                SearchProviderSelection(
                    provider=ProviderRef(id="patentsview", kind="search"),
                    adapter_id="patentsview-search",
                    yaml_priority=1,
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
                    ) in enumerate(_BATCH_THREE_SEARCH_ONLY_BINDINGS, start=100)
                ),
                *(
                    SearchProviderSelection(
                        provider=ProviderRef(id=manifest.id, kind="search"),
                        adapter_id=next(
                            adapter.id
                            for adapter in manifest.adapters
                            if adapter.capability == "search"
                        ),
                        yaml_priority=priority,
                    )
                    for priority, (
                        manifest,
                        _search_spec,
                        _fetch_spec,
                        _search_type,
                        _fetch_type,
                        _client_factory,
                    ) in enumerate(_BATCH_THREE_MULTI_BINDINGS, start=200)
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
                            for binding in _BATCH_FOUR_SEARCH_BINDINGS
                            if binding[0].id not in _LEGACY_DEFAULT_PROVIDER_IDS
                        ),
                        start=300,
                    )
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
        provider_adapter_ids={
            "arxiv_fulltext": "arxiv_fulltext-fetch",
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
