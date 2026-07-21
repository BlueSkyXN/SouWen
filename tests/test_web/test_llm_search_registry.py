"""Deterministic foundation tests for LLM-search scheme/source contracts."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from souwen.config import LLMSearchGatewayConfig, SouWenConfig, SourceChannelConfig
from souwen.registry.adapter import MethodSpec
from souwen.registry.meta import (
    has_required_credentials,
    is_valid_config_field_reference,
    missing_credential_fields,
)
from souwen.web.llm_search import (
    ConcreteSearchSourceSpec,
    SearchDeadlineBudget,
    SearchSchemeSpec,
    gateway_credential_fields,
    resolve_concrete_source_config,
)
from souwen.web.llm_search.registry import SearchSchemeRegistry


def _build_request(**kwargs):
    return kwargs


def _parse_response(payload, **_kwargs):
    return payload


def _scheme(**overrides) -> SearchSchemeSpec:
    values = {
        "scheme_id": "fixture_ark_annotations_v1",
        "gateway_id": "uniapi",
        "upstream_channel": "volcengine_ark",
        "protocol": "responses",
        "endpoint_kind": "responses",
        "tool_schema": "ark_web_search_v1",
        "candidate_contract": "structured_result_list",
        "default_timeout_seconds": 45,
        "source_grade": True,
        "request_builder": _build_request,
        "response_parser": _parse_response,
    }
    values.update(overrides)
    return SearchSchemeSpec(**values)


def _source(source_id: str = "uniapi_ark_deepseek", **overrides) -> ConcreteSearchSourceSpec:
    values = {
        "source_id": source_id,
        "scheme_id": "fixture_ark_annotations_v1",
        "model_id": "deepseek-v3-2-251201",
        "last_verified_at": datetime(2026, 7, 20, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return ConcreteSearchSourceSpec(**values)


class _Client:
    async def search(self):  # pragma: no cover - projection only
        raise NotImplementedError


def test_scheme_and_source_ids_are_strict_and_model_id_is_exact() -> None:
    with pytest.raises(ValueError, match="end with _vN"):
        _scheme(scheme_id="uniapi_ark_annotations")
    with pytest.raises(ValueError, match="provided together"):
        _scheme(response_parser=None)
    with pytest.raises(ValueError, match="candidate_contract"):
        _scheme(candidate_contract="typo")
    with pytest.raises(ValueError, match="request_builder must be callable"):
        _scheme(request_builder="not-callable", response_parser=object())
    with pytest.raises(ValueError, match="leading or trailing"):
        _source(model_id=" deepseek-v3-2-251201 ")
    with pytest.raises(ValueError, match="stability"):
        _source(stability="experimantal", default_enabled=True)
    with pytest.raises(ValueError, match="default to disabled"):
        _source(default_enabled=True)


def test_registry_rejects_duplicate_source_ids_and_identity_aliases() -> None:
    registry = SearchSchemeRegistry()
    scheme = registry.register_scheme(_scheme())
    with pytest.raises(ValueError, match="duplicate LLM-search scheme"):
        registry.register_scheme(scheme)
    registry.register_source(_source())

    with pytest.raises(ValueError, match="duplicate LLM-search source ID"):
        registry.register_source(_source())
    with pytest.raises(ValueError, match="already belongs"):
        registry.register_source(_source("uniapi_ark_deepseek_alias"))

    assert (
        registry.source_id_for("fixture_ark_annotations_v1", "deepseek-v3-2-251201")
        == "uniapi_ark_deepseek"
    )

    second = registry.register_source(
        _source(
            "uniapi_ark_doubao",
            model_id="doubao-seed-2-0-lite-260428",
        )
    )
    assert registry.get_scheme(scheme.scheme_id) is scheme
    assert registry.get_source(second.source_id) is second
    assert registry.source_id_for(scheme.scheme_id, second.model_id) == "uniapi_ark_doubao"


def test_registry_requires_known_executable_scheme() -> None:
    registry = SearchSchemeRegistry()
    with pytest.raises(ValueError, match="unknown scheme"):
        registry.register_source(_source())

    registry.register_scheme(_scheme(request_builder=None, response_parser=None))
    with pytest.raises(ValueError, match="not source-grade and executable"):
        registry.register_source(_source())


def test_projection_uses_canonical_source_adapter_and_gateway_requirements() -> None:
    registry = SearchSchemeRegistry()
    registry.register_scheme(_scheme())
    registry.register_source(_source(timeout_seconds=60))

    adapter = registry.project_source_adapter(
        "uniapi_ark_deepseek",
        description="fixture source",
        client_loader=lambda: _Client,
    )

    assert adapter.name == "uniapi_ark_deepseek"
    assert adapter.resolved_credential_fields == gateway_credential_fields("uniapi")
    assert adapter.config_field == "llm_search_gateways.uniapi.api_key"
    assert is_valid_config_field_reference(adapter.config_field)
    assert all(is_valid_config_field_reference(field) for field in adapter.credential_fields)
    assert adapter.default_enabled is False
    assert adapter.runtime_default_enabled is False
    assert adapter.default_for == frozenset()
    assert adapter.stability == "experimental"
    assert adapter.methods["search"].timeout_seconds == 60
    assert adapter.llm_search_identity == (
        "fixture_ark_annotations_v1",
        "deepseek-v3-2-251201",
    )

    custom = registry.project_source_adapter(
        "uniapi_ark_deepseek",
        description="fixture source",
        client_loader=lambda: _Client,
        methods={
            "search": MethodSpec(
                "custom_search",
                param_map={"limit": "max_results"},
            )
        },
    )
    assert custom.methods["search"].method_name == "custom_search"
    assert custom.methods["search"].param_map == {"limit": "max_results"}
    assert custom.methods["search"].timeout_seconds == 60

    with pytest.raises(ValueError, match="requires a search MethodSpec"):
        registry.project_source_adapter(
            "uniapi_ark_deepseek",
            description="fixture source",
            client_loader=lambda: _Client,
            methods={"fetch": MethodSpec("fetch")},
        )
    with pytest.raises(ValueError, match="timeout conflicts"):
        registry.project_source_adapter(
            "uniapi_ark_deepseek",
            description="fixture source",
            client_loader=lambda: _Client,
            methods={"search": MethodSpec("search", timeout_seconds=10)},
        )


def test_canonical_registry_rejects_identity_aliases_from_separate_scheme_registries(
    clean_registry,
) -> None:
    from souwen.registry.views import _reg_external

    first = SearchSchemeRegistry()
    first.register_scheme(_scheme())
    first.register_source(_source())
    assert _reg_external(
        first.project_source_adapter(
            "uniapi_ark_deepseek",
            description="first fixture source",
            client_loader=lambda: _Client,
        )
    )

    second = SearchSchemeRegistry()
    second.register_scheme(_scheme())
    second.register_source(_source("uniapi_ark_deepseek_alias"))
    assert (
        _reg_external(
            second.project_source_adapter(
                "uniapi_ark_deepseek_alias",
                description="aliased fixture source",
                client_loader=lambda: _Client,
            )
        )
        is False
    )


def test_shared_gateway_availability_uses_same_registry_meta_contract() -> None:
    registry = SearchSchemeRegistry()
    registry.register_scheme(_scheme())
    source = registry.register_source(_source())
    adapter = registry.project_source_adapter(
        source.source_id,
        description="fixture source",
        client_loader=lambda: _Client,
    )
    config = SouWenConfig(
        llm_search_gateways={
            "uniapi": LLMSearchGatewayConfig(
                api_key="shared-secret",
                base_url="https://gateway.example.com/v1",
            )
        }
    )

    assert has_required_credentials(config, source.source_id, adapter) is True
    assert missing_credential_fields(config, source.source_id, adapter) == []

    missing_url = SouWenConfig(
        llm_search_gateways={"uniapi": LLMSearchGatewayConfig(api_key="shared-secret")}
    )
    assert has_required_credentials(missing_url, source.source_id, adapter) is False
    assert missing_credential_fields(missing_url, source.source_id, adapter) == [
        "llm_search_gateways.uniapi.base_url"
    ]

    invalid_source_url = SouWenConfig(
        llm_search_gateways=config.llm_search_gateways,
        sources={
            source.source_id: SourceChannelConfig(
                enabled=True,
                base_url="file:///private/gateway",
            )
        },
    )
    assert has_required_credentials(invalid_source_url, source.source_id, adapter) is False
    assert missing_credential_fields(invalid_source_url, source.source_id, adapter) == [
        "llm_search_gateways.uniapi.base_url"
    ]
    with pytest.raises(ValueError, match="http/https URL"):
        resolve_concrete_source_config(invalid_source_url, _scheme(), source)


async def test_projected_source_uses_one_canonical_availability_contract(
    clean_registry,
    monkeypatch,
) -> None:
    from souwen.doctor import check_all, summarize_statuses
    from souwen.feature_matrix import RuntimeProbe
    from souwen.registry.catalog import available_source_catalog, public_source_catalog_payload
    from souwen.registry.views import _reg_external
    from souwen.server.routes.admin.sources import get_source_config as get_admin_source_config
    import souwen.config as config_module

    registry = SearchSchemeRegistry()
    scheme = registry.register_scheme(_scheme())
    source = registry.register_source(_source())
    adapter = registry.project_source_adapter(
        source.source_id,
        description="fixture source",
        client_loader=lambda: _Client,
    )
    assert _reg_external(adapter) is True

    current_config = {
        "value": SouWenConfig(
            edition="full",
            llm_search_gateways={
                "uniapi": LLMSearchGatewayConfig(
                    api_key="shared-secret",
                    base_url="https://shared.example.com/v1",
                )
            },
            sources={source.source_id: SourceChannelConfig(timeout=70)},
        )
    }
    monkeypatch.setattr("souwen.doctor.get_config", lambda: current_config["value"])
    monkeypatch.setattr(
        "souwen.doctor.probe_adapter_runtime",
        lambda _adapter: RuntimeProbe(True, ""),
    )

    def surfaces() -> tuple[dict, dict, SouWenConfig]:
        config = current_config["value"]
        catalog_item = next(
            item
            for item in public_source_catalog_payload(config)["sources"]
            if item["name"] == source.source_id
        )
        doctor_item = next(item for item in check_all() if item["name"] == source.source_id)
        return catalog_item, doctor_item, config

    async def admin_surface() -> dict:
        with monkeypatch.context() as scoped:
            scoped.setattr(config_module, "get_config", lambda: current_config["value"])
            return await get_admin_source_config(source.source_id)

    catalog_item, doctor_item, config = surfaces()
    admin_item = await admin_surface()
    assert source.source_id not in available_source_catalog(config)
    for item in (catalog_item, doctor_item, admin_item):
        assert item["available"] is False
        assert item["missing_credential_fields"] == []
        assert item["config_valid"] is True
    assert doctor_item["enabled"] is False
    assert admin_item["enabled"] is False

    cases = [
        (
            SouWenConfig(
                edition="full",
                llm_search_gateways={
                    "uniapi": LLMSearchGatewayConfig(base_url="https://shared.example.com/v1")
                },
                sources={source.source_id: SourceChannelConfig(enabled=True)},
            ),
            "llm_search_gateways.uniapi.api_key",
            "",
        ),
        (
            SouWenConfig(
                edition="full",
                llm_search_gateways={"uniapi": LLMSearchGatewayConfig(api_key="shared-secret")},
                sources={source.source_id: SourceChannelConfig(enabled=True)},
            ),
            "llm_search_gateways.uniapi.base_url",
            "",
        ),
        (
            SouWenConfig(
                edition="full",
                llm_search_gateways={
                    "uniapi": LLMSearchGatewayConfig(
                        api_key="shared-secret",
                        base_url="https://shared.example.com/v1",
                    )
                },
                sources={
                    source.source_id: SourceChannelConfig(
                        enabled=True,
                        base_url="file:///private/gateway",
                    )
                },
            ),
            "llm_search_gateways.uniapi.base_url",
            f"invalid source base_url: sources.{source.source_id}.base_url",
        ),
    ]
    for config, expected_missing, expected_config_reason in cases:
        current_config["value"] = config
        catalog_item, doctor_item, _ = surfaces()
        admin_item = await admin_surface()
        for item in (catalog_item, doctor_item, admin_item):
            assert item["available"] is False
            assert item["missing_credential_fields"] == [expected_missing]
            assert "private/gateway" not in str(item)
        assert catalog_item["config_reason"] == expected_config_reason
        assert admin_item["config_reason"] == expected_config_reason
        assert doctor_item["config_reason"] == (
            expected_config_reason or f"missing configuration: {expected_missing}"
        )
        assert catalog_item["config_valid"] is (not expected_config_reason)
        assert doctor_item["config_valid"] is (not expected_config_reason)
        assert admin_item["config_valid"] is (not expected_config_reason)

    current_config["value"] = SouWenConfig(
        edition="full",
        llm_search_gateways={
            "uniapi": LLMSearchGatewayConfig(
                api_key="shared-secret",
                base_url="https://shared.example.com/v1",
            )
        },
        sources={
            source.source_id: SourceChannelConfig(
                enabled=True,
                params={"model": "forbidden-model-value"},
            )
        },
    )
    catalog_item, doctor_item, _ = surfaces()
    admin_item = await admin_surface()
    expected_reason_path = f"sources.{source.source_id}.params.model"
    for item in (catalog_item, doctor_item, admin_item):
        assert item["available"] is False
        assert item["missing_credential_fields"] == []
        assert item["config_reason"].endswith(expected_reason_path)
        assert "forbidden-model-value" not in str(item)
    assert catalog_item["config_valid"] is False
    assert doctor_item["config_valid"] is False
    assert admin_item["config_valid"] is False
    assert doctor_item["status"] == "unavailable"
    counts = summarize_statuses([doctor_item])
    assert counts["ok"] == 0
    assert counts["available"] == 0
    assert counts["unavailable"] == 1

    with pytest.raises(ValueError, match="http/https URL"):
        resolve_concrete_source_config(cases[-1][0], scheme, source)
    with pytest.raises(ValueError, match="cannot override immutable fields"):
        resolve_concrete_source_config(current_config["value"], scheme, source)


def test_runtime_resolution_is_fieldwise_and_default_disabled() -> None:
    scheme = _scheme()
    source = _source(timeout_seconds=55)
    config = SouWenConfig(
        llm_search_gateways={
            "uniapi": LLMSearchGatewayConfig(
                api_key="shared-secret",
                base_url="https://shared.example.com/v1",
            )
        },
        sources={
            source.source_id: SourceChannelConfig(
                enabled=True,
                api_key="source-secret",
                timeout=70,
                params={"max_keyword": 3},
            )
        },
    )

    resolved = resolve_concrete_source_config(config, scheme, source)

    assert resolved.available is True
    assert resolved.timeout_seconds == 70
    assert resolved.params == {"max_keyword": 3}
    assert resolved.api_key == "source-secret"
    assert resolved.base_url == "https://shared.example.com/v1"
    rendered = repr(resolved)
    assert "source-secret" not in rendered
    assert "shared.example.com" not in rendered

    implicit = resolve_concrete_source_config(
        SouWenConfig(llm_search_gateways=config.llm_search_gateways),
        scheme,
        source,
    )
    assert implicit.enabled is False
    assert implicit.available is False
    assert implicit.timeout_seconds == 55


def test_runtime_override_does_not_implicitly_enable_experimental_source() -> None:
    scheme = _scheme()
    source = _source(timeout_seconds=55)
    config = SouWenConfig(
        llm_search_gateways={
            "uniapi": LLMSearchGatewayConfig(
                api_key="shared-secret",
                base_url="https://shared.example.com/v1",
            )
        },
        sources={
            source.source_id: SourceChannelConfig(
                timeout=70,
                params={"max_keyword": 3},
            )
        },
    )

    resolved = resolve_concrete_source_config(config, scheme, source)

    assert "enabled" not in config.sources[source.source_id].model_fields_set
    assert resolved.enabled is False
    assert resolved.available is False
    assert resolved.timeout_seconds == 70


@pytest.mark.parametrize("field", ["model", "model_id", "scheme_id", "gateway_id"])
def test_runtime_params_cannot_override_identity(field: str) -> None:
    scheme = _scheme()
    source = _source()
    config = SouWenConfig(
        sources={source.source_id: SourceChannelConfig(params={field: "override"})}
    )

    with pytest.raises(ValueError, match="cannot override immutable fields"):
        resolve_concrete_source_config(config, scheme, source)


def test_deadline_budget_is_monotonic_and_never_resets_between_attempts() -> None:
    now = [100.0]
    budget = SearchDeadlineBudget(75, _clock=lambda: now[0])

    assert budget.timeout_for(45) == 45
    now[0] += 40
    assert budget.timeout_for(45) == 35
    now[0] += 35
    assert budget.expired is True
    with pytest.raises(TimeoutError, match="deadline exhausted"):
        budget.timeout_for(45)
