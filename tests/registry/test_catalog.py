"""正式 source catalog 投影测试。"""

from __future__ import annotations

from souwen.config import SouWenConfig
from souwen.registry.adapter import (
    CATALOG_VISIBILITIES,
    SOURCE_CATEGORIES,
    MethodSpec,
    SourceAdapter,
)
from souwen.registry.catalog import (
    SourceCatalogEntry,
    available_source_catalog,
    default_source_map,
    public_source_catalog_payload,
    public_source_catalog,
    source_catalog,
    source_categories,
    sources_by_category,
)
from souwen.registry.loader import lazy
from souwen.registry import all_adapters, defaults_for, external_plugins, fetch_providers
from souwen.registry.views import _reg_external
from souwen.web.fetch import get_fetch_handlers


def test_source_categories_have_stable_metadata() -> None:
    categories = source_categories()
    assert {item.key for item in categories} == SOURCE_CATEGORIES
    assert [item.key for item in categories] == [
        "paper",
        "patent",
        "web_general",
        "web_professional",
        "social",
        "office",
        "developer",
        "knowledge",
        "cn_tech",
        "video",
        "archive",
        "fetch",
    ]
    for index, item in enumerate(categories):
        assert item.label
        assert item.order > 0
        if index:
            assert categories[index - 1].order < item.order


def test_every_adapter_projects_to_catalog_entry() -> None:
    catalog = source_catalog()
    assert catalog
    assert all(isinstance(entry, SourceCatalogEntry) for entry in catalog.values())
    for name, entry in catalog.items():
        assert entry.name == name
        assert entry.category in SOURCE_CATEGORIES
        assert entry.visibility in CATALOG_VISIBILITIES
        assert entry.capabilities == tuple(sorted(entry.capabilities))
        assert entry.risk_reasons == tuple(sorted(entry.risk_reasons))
        assert entry.default_for == tuple(sorted(entry.default_for))


def test_formal_fields_project_to_catalog_categories_and_visibility() -> None:
    catalog = source_catalog()
    assert catalog["duckduckgo"].category == "web_general"
    assert catalog["tavily"].category == "web_professional"
    assert catalog["wikipedia"].category == "knowledge"
    assert catalog["wayback"].category == "archive"

    assert catalog["unpaywall"].visibility == "hidden"
    assert "unpaywall" not in public_source_catalog()

    assert catalog["patentsview"].visibility == "public"
    assert catalog["patentsview"].auth_requirement == "required"
    assert catalog["patentsview"].config_field == "patentsview_api_key"
    assert catalog["patentsview"].credential_fields == ("patentsview_api_key",)
    assert catalog["patentsview"].available_by_default is False
    assert "patentsview" in public_source_catalog()

    assert catalog["pqai"].visibility == "public"
    assert catalog["pqai"].auth_requirement == "required"
    assert catalog["pqai"].config_field == "pqai_api_token"
    assert catalog["pqai"].credential_fields == ("pqai_api_token",)
    assert catalog["pqai"].available_by_default is False
    assert "pqai" in public_source_catalog()


def test_sources_by_category_uses_formal_category_keys() -> None:
    web_general = sources_by_category("web_general")
    web_professional = sources_by_category("web_professional")
    assert "duckduckgo" in {entry.name for entry in web_general}
    assert "tavily" in {entry.name for entry in web_professional}
    assert sources_by_category("general") == []


def test_default_source_map_references_existing_safe_entries() -> None:
    catalog = source_catalog()
    defaults = default_source_map()
    assert defaults
    for key, names in defaults.items():
        assert ":" in key
        for name in names:
            entry = catalog[name]
            assert key in entry.default_for
            assert entry.visibility == "public"
            assert entry.risk_level != "high"
            assert entry.stability != "deprecated"


def test_adapter_registration_order_snapshot() -> None:
    assert tuple(all_adapters()) == (
        "openalex",
        "eric",
        "osti",
        "semantic_scholar",
        "crossref",
        "arxiv",
        "dblp",
        "core",
        "pubmed",
        "biorxiv",
        "zotero",
        "huggingface",
        "europepmc",
        "pmc",
        "doaj",
        "zenodo",
        "hal",
        "openaire",
        "iacr",
        "ieee_xplore",
        "unpaywall",
        "patentsview",
        "pqai",
        "epo_ops",
        "uspto_odp",
        "the_lens",
        "cnipa",
        "patsnap",
        "google_patents",
        "duckduckgo",
        "duckduckgo_news",
        "duckduckgo_images",
        "duckduckgo_videos",
        "yahoo",
        "brave",
        "google",
        "bing",
        "bing_cn",
        "startpage",
        "baidu",
        "mojeek",
        "yandex",
        "serpapi",
        "brave_api",
        "serper",
        "scrapingdog",
        "metaso",
        "uniapi_ark_annotations_deepseek_v3_2_251201",
        "uniapi_ark_annotations_doubao_seed_2_0_lite_260428",
        "tavily",
        "exa",
        "perplexity",
        "firecrawl",
        "linkup",
        "xcrawl",
        "zhipuai",
        "aliyun_iqs",
        "kimi_code",
        "searxng",
        "whoogle",
        "websurfx",
        "reddit",
        "twitter",
        "facebook",
        "weibo",
        "zhihu",
        "youtube",
        "bilibili",
        "wikipedia",
        "github",
        "stackoverflow",
        "csdn",
        "juejin",
        "linuxdo",
        "nodeseek",
        "hostloc",
        "v2ex",
        "coolapk",
        "xiaohongshu",
        "community_cn",
        "feishu_drive",
        "wayback",
        "builtin",
        "jina_reader",
        "arxiv_fulltext",
        "crawl4ai",
        "scrapling",
        "scrapfly",
        "diffbot",
        "scrapingbee",
        "zenrows",
        "scraperapi",
        "apify",
        "cloudflare",
        "newspaper",
        "readability",
        "mcp",
        "site_crawler",
        "deepwiki",
    )


def test_default_source_order_snapshot() -> None:
    expected = {
        "paper:search": ["openalex", "crossref", "arxiv", "dblp", "pubmed", "biorxiv"],
        "patent:search": ["google_patents"],
        "web:search": ["duckduckgo", "bing"],
        "web:search_news": ["duckduckgo_news"],
        "web:search_images": ["duckduckgo_images"],
        "web:search_videos": ["duckduckgo_videos"],
        "video:search": ["youtube", "bilibili"],
        "knowledge:search": ["wikipedia"],
        "developer:search": ["github", "stackoverflow"],
        "archive:archive_lookup": ["wayback"],
        "fetch:fetch": ["builtin"],
    }
    assert {
        "paper:search": defaults_for("paper", "search"),
        "patent:search": defaults_for("patent", "search"),
        "web:search": defaults_for("web", "search"),
        "web:search_news": defaults_for("web", "search_news"),
        "web:search_images": defaults_for("web", "search_images"),
        "web:search_videos": defaults_for("web", "search_videos"),
        "video:search": defaults_for("video", "search"),
        "knowledge:search": defaults_for("knowledge", "search"),
        "developer:search": defaults_for("developer", "search"),
        "archive:archive_lookup": defaults_for("archive", "archive_lookup"),
        "fetch:fetch": defaults_for("fetch", "fetch"),
    } == expected
    assert {key: list(names) for key, names in default_source_map().items()} == expected


def test_non_public_high_risk_and_deprecated_sources_are_not_default_available() -> None:
    for entry in source_catalog().values():
        unsafe = (
            entry.visibility != "public"
            or entry.risk_level == "high"
            or entry.stability in {"deprecated", "experimental"}
        )
        if unsafe:
            assert entry.available_by_default is False


def test_required_and_self_hosted_sources_are_not_available_by_default() -> None:
    catalog = source_catalog()
    assert catalog["tavily"].auth_requirement == "required"
    assert catalog["tavily"].available_by_default is False
    assert catalog["searxng"].auth_requirement == "self_hosted"
    assert catalog["searxng"].available_by_default is False


def test_available_source_catalog_matches_runtime_credentials_and_enabled_state() -> None:
    default_available = available_source_catalog(SouWenConfig())
    assert "openalex" in default_available
    assert "duckduckgo" in default_available
    assert "tavily" not in default_available
    assert "searxng" not in default_available
    assert "unpaywall" not in default_available

    disabled = available_source_catalog(SouWenConfig(sources={"duckduckgo": {"enabled": False}}))
    assert "duckduckgo" not in disabled

    configured = available_source_catalog(
        SouWenConfig(sources={"searxng": {"base_url": "https://search.example"}})
    )
    assert "searxng" in configured

    basic_available = available_source_catalog(SouWenConfig(edition="basic"))
    assert "arxiv" in basic_available
    assert "openalex" not in basic_available


def test_runtime_default_disabled_source_requires_explicit_enable(clean_registry) -> None:
    adapter = SourceAdapter(
        name="runtime_default_disabled_probe",
        domain="web",
        integration="official_api",
        description="runtime default probe",
        config_field=None,
        client_loader=lambda: object,
        methods={"search": MethodSpec("search")},
        auth_requirement="none",
        runtime_default_enabled=False,
    )
    assert _reg_external(adapter) is True

    default_config = SouWenConfig(
        edition="full",
        sources={adapter.name: {"timeout": 45}},
    )
    assert adapter.name not in available_source_catalog(default_config)

    enabled_config = SouWenConfig(
        edition="full",
        sources={adapter.name: {"enabled": True, "timeout": 45}},
    )
    assert adapter.name in available_source_catalog(enabled_config)


def test_public_source_catalog_payload_includes_edition_metadata() -> None:
    payload = public_source_catalog_payload(SouWenConfig(edition="basic"))
    sources = {item["name"]: item for item in payload["sources"]}

    arxiv = sources["arxiv"]
    assert arxiv["min_edition"] == "basic"
    assert arxiv["edition_available"] is True
    assert arxiv["edition_reason"] == ""
    assert isinstance(arxiv["runtime_available"], bool)
    assert isinstance(arxiv["runtime_reason"], str)
    assert arxiv["available"] is True

    openalex = sources["openalex"]
    assert openalex["min_edition"] == "pro"
    assert openalex["edition_available"] is False
    assert "source 'openalex' requires edition=pro" in openalex["edition_reason"]
    assert openalex["available"] is False


def test_public_source_catalog_payload_exposes_runtime_without_redefining_available(
    monkeypatch,
) -> None:
    """The additive runtime axis must not silently change the compatibility field."""
    from souwen.feature_matrix import RuntimeProbe

    def fake_probe(adapter: SourceAdapter) -> RuntimeProbe:
        if adapter.name == "openalex":
            return RuntimeProbe(False, "openalex: missing modules: optional_sdk")
        return RuntimeProbe(True)

    monkeypatch.setattr("souwen.feature_matrix.probe_adapter_runtime", fake_probe)

    payload = public_source_catalog_payload(SouWenConfig(edition="pro"))
    openalex = next(item for item in payload["sources"] if item["name"] == "openalex")

    assert openalex["edition_available"] is True
    assert openalex["runtime_available"] is False
    assert openalex["runtime_reason"] == "openalex: missing modules: optional_sdk"
    assert openalex["available"] is True


def test_public_source_catalog_payload_sanitizes_client_loader_exception(
    clean_registry,
) -> None:
    """Public catalog must not expose paths, DSNs, or tokens from a failing plugin loader."""
    secret_text = (
        "failed at /Users/private/customer/plugin.py "
        "postgresql://user:password@db.internal/source token=runtime-secret"
    )

    def failing_loader() -> type:
        raise RuntimeError(secret_text)

    adapter = SourceAdapter(
        name="catalog_sensitive_loader_probe",
        domain="web",
        integration="official_api",
        description="sensitive loader probe",
        config_field=None,
        client_loader=failing_loader,
        methods={"search": MethodSpec("search")},
        auth_requirement="none",
    )
    assert _reg_external(adapter) is True

    payload = public_source_catalog_payload(SouWenConfig(edition="full"))
    source = next(item for item in payload["sources"] if item["name"] == adapter.name)
    serialized = str(payload)

    assert source["runtime_available"] is False
    assert source["runtime_reason"] == ("catalog_sensitive_loader_probe: client loader unavailable")
    assert secret_text not in serialized
    assert "/Users/private" not in serialized
    assert "postgresql://" not in serialized
    assert "runtime-secret" not in serialized


def test_public_source_catalog_payload_does_not_probe_edition_gated_sources(
    monkeypatch,
) -> None:
    """Basic catalog discovery must not import implementations excluded by its edition."""
    from souwen.feature_matrix import RuntimeProbe

    probed: list[str] = []

    def fake_probe(adapter: SourceAdapter) -> RuntimeProbe:
        probed.append(adapter.name)
        return RuntimeProbe(True)

    monkeypatch.setattr("souwen.feature_matrix.probe_adapter_runtime", fake_probe)

    payload = public_source_catalog_payload(SouWenConfig(edition="basic"))
    openalex = next(item for item in payload["sources"] if item["name"] == "openalex")

    assert "openalex" not in probed
    assert openalex["edition_available"] is False
    assert openalex["runtime_available"] is False
    assert openalex["runtime_reason"] == (
        "runtime not probed because source 'openalex' requires edition=pro, current edition=basic"
    )
    assert openalex["available"] is False


def test_catalog_fetch_providers_have_runtime_handlers() -> None:
    """Source catalog 中的 fetch provider 必须能派发到 fetch handler。"""
    external_plugin_names = set(external_plugins())
    registry_fetch_provider_names = {
        adapter.name for adapter in fetch_providers() if adapter.name not in external_plugin_names
    }
    handler_names = set(get_fetch_handlers())
    assert registry_fetch_provider_names <= handler_names


def test_runtime_plugin_uses_public_category_tag_and_plugin_distribution(
    clean_registry,
) -> None:
    adapter = SourceAdapter(
        name="catalog_runtime_web_probe",
        domain="web",
        integration="official_api",
        description="runtime catalog probe",
        config_field="tavily_api_key",
        client_loader=lazy("souwen.web.tavily:TavilyClient"),
        methods={"search": MethodSpec("search")},
        auth_requirement="required",
        credential_fields=("tavily_api_key",),
        tags=frozenset({"category:professional"}),
    )

    assert _reg_external(adapter) is True
    entry = source_catalog()["catalog_runtime_web_probe"]
    assert entry.category == "web_professional"
    assert entry.distribution == "plugin"


def test_explicit_category_and_visibility_override_compat_defaults(clean_registry) -> None:
    adapter = SourceAdapter(
        name="catalog_internal_probe",
        domain="web",
        integration="scraper",
        description="internal catalog probe",
        config_field=None,
        client_loader=lazy("souwen.web.duckduckgo:DuckDuckGoClient"),
        methods={"search": MethodSpec("search")},
        category="web_professional",
        catalog_visibility="internal",
    )

    assert _reg_external(adapter) is True
    entry = source_catalog()["catalog_internal_probe"]
    assert entry.category == "web_professional"
    assert entry.visibility == "internal"
    assert entry.available_by_default is False
    assert "catalog_internal_probe" not in public_source_catalog()
