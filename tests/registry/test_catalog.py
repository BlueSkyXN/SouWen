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
    public_source_catalog,
    source_catalog,
    source_categories,
    sources_by_category,
)
from souwen.registry.loader import lazy
from souwen.registry import external_plugins, fetch_providers
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
    assert catalog["patentsview"].visibility == "hidden"
    assert catalog["pqai"].visibility == "hidden"
    assert "unpaywall" not in public_source_catalog()
    assert "patentsview" not in public_source_catalog()
    assert "pqai" not in public_source_catalog()


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
