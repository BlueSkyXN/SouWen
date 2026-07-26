from __future__ import annotations

import json

from souwen.feature_matrix import (
    FetchProviderRuntimeStatus,
    ProbeResult,
    RuntimeProbe,
    probe_adapter_runtime,
    fetch_provider_runtime_projection,
    probe_modules,
    probe_optional_runtime,
    probe_capabilities,
    probe_results_to_dict,
    public_adapter_runtime_probe,
    sanitize_public_runtime_probe,
)
from souwen.registry.adapter import FETCH_DOMAIN, MethodSpec, SourceAdapter


def _adapter(name: str, *, extra: str | None = None, broken: bool = False) -> SourceAdapter:
    def loader() -> type:
        if broken:
            raise RuntimeError("private token")
        return object

    return SourceAdapter(
        name=name,
        domain=FETCH_DOMAIN,
        integration="open_api",
        description=name,
        config_field=None,
        client_loader=loader,
        methods={"fetch": MethodSpec("run")},
        auth_requirement="none",
        package_extra=extra,
    )


def test_probe_reports_all_declared_adapters_without_tier_filter(monkeypatch) -> None:
    import souwen.registry as registry

    builtin = _adapter("builtin")
    broken = _adapter("broken", broken=True)
    monkeypatch.setattr(registry, "all_adapters", lambda: {builtin.name: builtin})
    monkeypatch.setattr(registry, "fetch_providers", lambda: [builtin, broken])

    result = probe_capabilities()

    assert result["sources"] == ProbeResult(("builtin",), ("builtin",))
    assert result["fetch_providers"].declared == ("broken", "builtin")
    assert result["fetch_providers"].available == ("builtin",)


def test_public_probe_redacts_loader_exception() -> None:
    result = public_adapter_runtime_probe(_adapter("broken", broken=True))
    assert result == RuntimeProbe(False, "broken: client loader unavailable")
    assert "private token" not in result.reason


def test_fetch_projection_reports_local_runtime_for_every_provider(monkeypatch) -> None:
    import souwen.registry as registry

    builtin = _adapter("builtin")
    broken = _adapter("broken", broken=True)
    monkeypatch.setattr(registry, "fetch_providers", lambda: [broken, builtin])

    statuses = {item.name: item for item in fetch_provider_runtime_projection()}
    assert statuses["builtin"] == FetchProviderRuntimeStatus("builtin", True)
    assert statuses["broken"].available is False


def test_probe_result_is_json_serializable() -> None:
    payload = probe_results_to_dict({"example": ProbeResult(("a",), ("a",))})
    assert json.loads(json.dumps(payload)) == {
        "example": {"declared": ["a"], "available": ["a"], "reason": ""}
    }


def test_module_and_adapter_probes_cover_missing_and_unknown_extras(monkeypatch) -> None:
    import souwen.feature_matrix as matrix

    monkeypatch.setattr(matrix.importlib.util, "find_spec", lambda _name: None)

    assert probe_modules(["missing_sdk"]) == RuntimeProbe(False, "missing modules: missing_sdk")
    assert probe_adapter_runtime(_adapter("unknown", extra="unknown_extra")) == RuntimeProbe(True)
    assert probe_adapter_runtime(_adapter("crawl", extra="crawl4ai")) == RuntimeProbe(
        False,
        "crawl: missing modules: crawl4ai",
    )


def test_optional_runtime_probe_covers_all_metadata_branches(monkeypatch) -> None:
    import souwen.feature_matrix as matrix

    assert probe_optional_runtime(_adapter("core")) == RuntimeProbe(True)
    assert probe_optional_runtime(_adapter("unknown", extra="unknown_extra")) == RuntimeProbe(True)

    monkeypatch.setattr(matrix, "_module_importable", lambda name: name == "crawl4ai")
    assert probe_optional_runtime(_adapter("crawl", extra="crawl4ai")) == RuntimeProbe(True)
    assert probe_optional_runtime(_adapter("web", extra="web")) == RuntimeProbe(True)


def test_public_sanitizer_preserves_only_maintained_missing_module_reason() -> None:
    runtime = RuntimeProbe(False, "fixture: missing modules: optional_sdk")
    assert sanitize_public_runtime_probe("fixture", runtime) is runtime


def test_package_extra_projection_reports_available_missing_and_unknown(monkeypatch) -> None:
    import souwen.feature_matrix as matrix

    adapters = [
        _adapter("crawl", extra="crawl4ai"),
        _adapter("unknown", extra="unknown_extra"),
        _adapter("web", extra="web"),
    ]
    monkeypatch.setattr(matrix, "_module_importable", lambda name: name == "crawl4ai")

    result = matrix._probe_package_extras(adapters)

    assert result.available == ("crawl4ai",)
    assert "unknown_extra: no optional module probe is declared" in result.reason
    assert "web: missing modules: trafilatura" in result.reason


def test_module_importable_sanitizes_find_spec_errors(monkeypatch) -> None:
    import souwen.feature_matrix as matrix

    def raise_value_error(_name):
        raise ValueError("broken spec")

    monkeypatch.setattr(matrix.importlib.util, "find_spec", raise_value_error)
    assert matrix._module_importable("broken") is False
