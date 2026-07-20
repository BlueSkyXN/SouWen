from __future__ import annotations

import json

from souwen.feature_matrix import (
    LLM_PROVIDER_MODULES,
    ProbeResult,
    RuntimeProbe,
    probe_adapter_runtime,
    probe_capabilities,
    probe_modules,
    probe_results_to_dict,
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
    mcp = _adapter("mcp", domain=FETCH_DOMAIN, loader_error=ImportError("missing optional mcp"))

    import souwen.registry as registry

    monkeypatch.setattr(registry, "all_adapters", lambda: {source.name: source})
    monkeypatch.setattr(registry, "fetch_providers", lambda: [builtin, mcp])
    monkeypatch.setattr(
        "souwen.feature_matrix.importlib.util.find_spec",
        lambda module: object() if module != "mcp" else None,
    )

    results = probe_capabilities("basic")

    assert results["sources"] == ProbeResult(
        declared=("basic_source",),
        available=("basic_source",),
    )
    assert results["fetch_providers"].declared == ("builtin", "mcp")
    assert results["fetch_providers"].available == ("builtin",)
    assert "mcp: ImportError: missing optional mcp" in results["fetch_providers"].reason
    assert results["mcp"] == ProbeResult(
        declared=True,
        available=False,
        reason="module 'mcp' is not importable",
    )


def test_probe_adapter_runtime_combines_loader_and_optional_modules(monkeypatch) -> None:
    mcp = _adapter("mcp", domain=FETCH_DOMAIN, package_extra="mcp")
    monkeypatch.setattr("souwen.feature_matrix.importlib.util.find_spec", lambda _module: None)

    assert probe_adapter_runtime(mcp) == RuntimeProbe(
        False,
        "mcp: missing modules: mcp",
    )
    assert probe_modules(("mcp", "another_module")) == RuntimeProbe(
        False,
        "missing modules: mcp, another_module",
    )


def test_probe_capabilities_reports_optional_package_extra_importability(monkeypatch) -> None:
    """Probe should expose missing optional extras without calling providers."""

    mcp = _adapter("mcp", domain=FETCH_DOMAIN, package_extra="mcp")
    readability = _adapter("readability", domain=FETCH_DOMAIN, package_extra="readability")
    scrapling = _adapter("scrapling", domain=FETCH_DOMAIN, package_extra="scrapling")

    import souwen.registry as registry

    monkeypatch.setattr(
        registry,
        "all_adapters",
        lambda: {adapter.name: adapter for adapter in (mcp, readability, scrapling)},
    )
    monkeypatch.setattr(registry, "fetch_providers", lambda: [mcp, readability, scrapling])
    monkeypatch.setattr(
        "souwen.feature_matrix.importlib.util.find_spec",
        lambda module: object() if module in {"mcp", "scrapling.fetchers"} else None,
    )

    results = probe_capabilities("full")

    assert results["package_extras"].declared == {
        "mcp": ("mcp",),
        "readability": ("readability",),
        "scrapling": ("scrapling.fetchers",),
    }
    assert results["package_extras"].available == ("mcp", "scrapling")
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
