from __future__ import annotations

import json

from souwen.feature_matrix import (
    FetchProviderRuntimeStatus,
    LLM_PROVIDER_MODULES,
    ProbeResult,
    RuntimeProbe,
    fetch_provider_runtime_projection,
    probe_adapter_runtime,
    probe_capabilities,
    probe_modules,
    probe_results_to_dict,
    public_adapter_runtime_probe,
    sanitize_public_runtime_probe,
)
from souwen.registry.adapter import FETCH_DOMAIN, MethodSpec, SourceAdapter


def _adapter(
    name: str,
    *,
    domain: str = "web",
    auth_requirement: str = "none",
    config_field: str | None = None,
    package_extra: str | None = None,
    loader_error: Exception | None = None,
) -> SourceAdapter:
    def _load() -> type:
        if loader_error is not None:
            raise loader_error
        return object

    return SourceAdapter(
        name=name,
        domain=domain,
        integration="open_api",
        description=f"{name} test adapter",
        config_field=config_field,
        client_loader=_load,
        methods={"fetch" if domain == FETCH_DOMAIN else "search": MethodSpec("run")},
        auth_requirement=auth_requirement,
        package_extra=package_extra,
    )


def test_probe_capabilities_reports_declared_and_importable_adapters(monkeypatch) -> None:
    """Probe should not hide declared capabilities whose package is missing."""

    source = _adapter("basic_source")
    builtin = _adapter("builtin", domain=FETCH_DOMAIN)
    site_crawler = _adapter(
        "site_crawler", domain=FETCH_DOMAIN, loader_error=ImportError("missing client")
    )

    import souwen.registry as registry

    monkeypatch.setattr(registry, "all_adapters", lambda: {source.name: source})
    monkeypatch.setattr(registry, "fetch_providers", lambda: [builtin, site_crawler])

    results = probe_capabilities("basic")

    assert results["sources"] == ProbeResult(
        declared=("basic_source",),
        available=("basic_source",),
    )
    assert results["fetch_providers"].declared == ("builtin", "site_crawler")
    assert results["fetch_providers"].available == ("builtin",)
    assert "site_crawler: ImportError: missing client" in results["fetch_providers"].reason


def test_probe_adapter_runtime_combines_loader_and_optional_modules(monkeypatch) -> None:
    readability = _adapter("readability", domain=FETCH_DOMAIN, package_extra="readability")
    monkeypatch.setattr("souwen.feature_matrix.importlib.util.find_spec", lambda _module: None)

    assert probe_adapter_runtime(readability) == RuntimeProbe(
        False,
        "readability: missing modules: readability",
    )
    assert probe_modules(("readability", "another_module")) == RuntimeProbe(
        False,
        "missing modules: readability, another_module",
    )


def test_public_adapter_runtime_probe_redacts_loader_exception(monkeypatch) -> None:
    secret = "postgresql://user:password@private.internal/db token=runtime-secret"
    broken = _adapter("broken", domain=FETCH_DOMAIN, loader_error=RuntimeError(secret))
    readability = _adapter("readability", domain=FETCH_DOMAIN, package_extra="readability")
    monkeypatch.setattr("souwen.feature_matrix.importlib.util.find_spec", lambda _module: None)

    assert public_adapter_runtime_probe(broken) == RuntimeProbe(
        False,
        "broken: client loader unavailable",
    )
    assert secret not in public_adapter_runtime_probe(broken).reason
    assert public_adapter_runtime_probe(readability) == RuntimeProbe(
        False,
        "readability: missing modules: readability",
    )
    assert sanitize_public_runtime_probe(
        "gated",
        RuntimeProbe(False, "runtime not probed because edition requires pro"),
    ) == RuntimeProbe(False, "runtime not probed because edition requires pro")


def test_fetch_provider_runtime_projection_separates_edition_and_missing_runtime(
    monkeypatch,
) -> None:
    """Basic declarations must not turn missing SDKs or pro providers into available IDs."""

    builtin = _adapter("builtin", domain=FETCH_DOMAIN)
    jina = _adapter("jina_reader", domain=FETCH_DOMAIN)
    site_crawler = _adapter("site_crawler", domain=FETCH_DOMAIN)

    import souwen.registry as registry

    monkeypatch.setattr(registry, "fetch_providers", lambda: [jina, site_crawler, builtin])
    monkeypatch.setattr("souwen.feature_matrix.importlib.util.find_spec", lambda _module: None)

    statuses = {item.name: item for item in fetch_provider_runtime_projection("basic")}

    assert statuses["builtin"] == FetchProviderRuntimeStatus(
        name="builtin",
        min_edition="basic",
        edition_available=True,
        runtime_available=True,
    )
    assert statuses["site_crawler"] == FetchProviderRuntimeStatus(
        name="site_crawler",
        min_edition="basic",
        edition_available=True,
        runtime_available=True,
    )
    assert statuses["jina_reader"].min_edition == "pro"
    assert statuses["jina_reader"].edition_available is False
    assert "requires edition=pro" in statuses["jina_reader"].edition_reason
    assert statuses["jina_reader"].runtime_available is False
    assert statuses["jina_reader"].runtime_reason.startswith("runtime not probed because ")


def test_fetch_provider_runtime_projection_reflects_full_browser_variant(
    monkeypatch,
) -> None:
    """A full Crawl4AI build must not claim the mutually exclusive Scrapling runtime."""

    crawl4ai = _adapter("crawl4ai", domain=FETCH_DOMAIN, package_extra="crawl4ai")
    scrapling = _adapter("scrapling", domain=FETCH_DOMAIN, package_extra="scrapling")

    import souwen.registry as registry

    monkeypatch.setattr(registry, "fetch_providers", lambda: [scrapling, crawl4ai])
    monkeypatch.setattr(
        "souwen.feature_matrix.importlib.util.find_spec",
        lambda module: object() if module == "crawl4ai" else None,
    )

    statuses = {item.name: item for item in fetch_provider_runtime_projection("full")}

    assert statuses["crawl4ai"].edition_available is True
    assert statuses["crawl4ai"].runtime_available is True
    assert statuses["crawl4ai"].available is True
    assert statuses["scrapling"].edition_available is True
    assert statuses["scrapling"].runtime_available is False
    assert statuses["scrapling"].runtime_reason == (
        "scrapling: missing modules: scrapling.fetchers"
    )
    assert statuses["scrapling"].available is False


def test_probe_capabilities_reports_optional_package_extra_importability(monkeypatch) -> None:
    """Probe should expose missing optional extras without calling providers."""

    readability = _adapter("readability", domain=FETCH_DOMAIN, package_extra="readability")
    scrapling = _adapter("scrapling", domain=FETCH_DOMAIN, package_extra="scrapling")

    import souwen.registry as registry

    monkeypatch.setattr(
        registry,
        "all_adapters",
        lambda: {adapter.name: adapter for adapter in (readability, scrapling)},
    )
    monkeypatch.setattr(registry, "fetch_providers", lambda: [readability, scrapling])
    monkeypatch.setattr(
        "souwen.feature_matrix.importlib.util.find_spec",
        lambda module: object() if module == "scrapling.fetchers" else None,
    )

    results = probe_capabilities("full")

    assert results["package_extras"].declared == {
        "readability": ("readability",),
        "scrapling": ("scrapling.fetchers",),
    }
    assert results["package_extras"].available == ("scrapling",)
    assert results["package_extras"].reason == "readability: missing modules: readability"


def test_probe_capabilities_uses_resolved_package_extra(monkeypatch) -> None:
    """Probe should include extras inferred from registry metadata."""

    scraper = SourceAdapter(
        name="duckduckgo",
        domain="web",
        integration="scraper",
        description="duckduckgo test adapter",
        config_field=None,
        client_loader=lambda: object,
        methods={"search": MethodSpec("run")},
        auth_requirement="none",
    )

    import souwen.registry as registry

    monkeypatch.setattr(registry, "all_adapters", lambda: {scraper.name: scraper})
    monkeypatch.setattr(registry, "fetch_providers", lambda: [])
    monkeypatch.setattr(
        "souwen.feature_matrix.importlib.util.find_spec",
        lambda module: object() if module == "curl_cffi" else None,
    )

    results = probe_capabilities("full")

    assert results["package_extras"].declared["scraper"] == ("curl_cffi",)
    assert "scraper" in results["package_extras"].available


def test_probe_capabilities_reports_unknown_package_extra(monkeypatch) -> None:
    """Unknown package extras should be visible instead of silently ignored."""

    custom = _adapter("custom_fetch", domain=FETCH_DOMAIN, package_extra="custom_extra")

    import souwen.registry as registry

    monkeypatch.setattr(registry, "all_adapters", lambda: {})
    monkeypatch.setattr(registry, "fetch_providers", lambda: [custom])
    monkeypatch.setattr("souwen.feature_matrix.importlib.util.find_spec", lambda _module: None)

    results = probe_capabilities("full")

    assert results["package_extras"].declared == {"custom_extra": ()}
    assert results["package_extras"].available == ()
    assert results["package_extras"].reason == (
        "custom_extra: no optional module probe is declared"
    )


def test_probe_capabilities_checks_llm_modules_without_calling_llm(monkeypatch) -> None:
    import souwen.registry as registry

    monkeypatch.setattr(registry, "all_adapters", lambda: {})
    monkeypatch.setattr(registry, "fetch_providers", lambda: [])

    def fake_find_spec(module: str) -> object | None:
        return object() if module == LLM_PROVIDER_MODULES["openai_chat"] else None

    monkeypatch.setattr("souwen.feature_matrix.importlib.util.find_spec", fake_find_spec)

    results = probe_capabilities("pro")

    assert results["llm_protocols"].declared == tuple(LLM_PROVIDER_MODULES)
    assert results["llm_protocols"].available == ("openai_chat",)
    assert results["llm_protocols"].reason == (
        "missing provider modules: openai_responses, anthropic_messages"
    )


def test_probe_results_to_dict_is_json_serializable() -> None:
    payload = probe_results_to_dict({"example": ProbeResult(("a",), ("a",), "")})

    assert payload == {
        "example": {
            "declared": ("a",),
            "available": ("a",),
            "reason": "",
        }
    }
    assert json.loads(json.dumps(payload)) == {
        "example": {
            "declared": ["a"],
            "available": ["a"],
            "reason": "",
        }
    }
