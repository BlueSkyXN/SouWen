"""Language-neutral checks for the accepted target contract, not current routes."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_target_fixtures_are_explicitly_non_runtime_and_deterministic() -> None:
    for name in (
        "target_api_contract_v2.json",
        "target_provider_manifest_v2.json",
    ):
        fixture = _read(name)
        assert fixture["fixture_version"] == 1
        assert fixture["target_only"] is True
        assert fixture["implemented_by_current_runtime"] is False
        assert json.loads(json.dumps(fixture, sort_keys=True)) == fixture


def test_target_api_closes_approved_decisions_without_claiming_current_routes() -> None:
    contract = _read("target_api_contract_v2.json")
    assert contract["api_major"] == 2
    assert contract["approved_decisions"] == [
        "Q-004",
        "Q-005",
        "Q-006",
        "Q-007",
        "Q-008",
        "API-Q-001",
        "REL-Q-001",
    ]

    operations = contract["operations"]
    assert isinstance(operations, dict)
    assert {operation["path"] for operation in operations.values()} == {
        "/api/v1/search",
        "/api/v1/llm-search",
        "/api/v1/fetch",
        "/api/v1/providers",
        "/healthz",
        "/readyz",
    }
    assert all(
        operation["security"] == "user_token"
        for key, operation in operations.items()
        if key not in {"healthz", "readyz"}
    )
    assert operations["healthz"]["security"] == operations["readyz"]["security"] == "none"

    validation = contract["validation"]
    assert validation["client_input_status"] == 400
    assert 422 in validation["not_canonical_statuses"]
    assert validation["specialist_statuses"] == [409, 413, 415]

    search = contract["search_policy"]
    assert search["missing_providers"] == "one_yaml_domain_capability_ordered_primary"
    assert search["fanout"] == "explicit_multiple_providers_only"
    assert search["merge"] == "equal_weight_rrf"
    assert search["rrf_k"] == 60
    assert search["deduplication_order"] == [
        "stable_domain_id",
        "canonical_url",
        "normalized_title_year",
    ]

    llm = contract["llm_search_policy"]
    assert llm["item_requires_evidence"] is True
    assert llm["answer_factual_paragraph_requires_stable_evidence_id"] is True
    assert llm["usage_always_present"] is True
    assert llm["unknown_usage_fields"] == "null"

    fetch = contract["fetch_policy"]
    assert fetch["target_count"] == {"minimum": 1, "maximum": 20}
    assert fetch["decompressed_response_hard_cap_bytes"] == 10 * 1024 * 1024
    assert fetch["default_content_code_points"] == 200000
    assert fetch["maximum_content_code_points"] == 1000000
    assert fetch["low_quality_non_empty_character_range"] == {"minimum": 1, "maximum": 63}

    aliases = contract["probe_aliases"]
    assert aliases["/health"]["canonical"] == "/healthz"
    assert aliases["/readiness"]["canonical"] == "/readyz"
    assert all(
        alias["same_handler"] and alias["same_payload"] and not alias["redirect"]
        for alias in aliases.values()
    )
    assert all(
        alias["retained_through"] == "2.x" and alias["earliest_removal"] == "3.0"
        for alias in aliases.values()
    )


def test_target_openapi_skeleton_matches_the_target_fixture() -> None:
    contract = _read("target_api_contract_v2.json")
    skeleton = _read("target_openapi_skeleton_v2.json")
    assert skeleton["openapi"] == "3.1.0"
    assert skeleton["x-souwen-api-major"] == contract["api_major"]
    assert skeleton["x-souwen-contract-stage"] == "target_skeleton_not_runtime"

    paths = skeleton["paths"]
    assert isinstance(paths, dict)
    for operation in contract["operations"].values():
        path = operation["path"]
        method = operation["method"].lower()
        assert path in paths
        assert method in paths[path]

    for alias_path, alias in contract["probe_aliases"].items():
        assert paths[alias_path]["get"]["x-souwen-alias-of"] == alias["canonical"]

    schemas = skeleton["components"]["schemas"]
    headers = skeleton["components"]["headers"]
    assert headers["X-SouWen-API-Major"]["schema"] == {"const": "2"}
    assert {
        "Retry-After",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    } <= set(headers)
    assert schemas["RequestContext"]["properties"]["api_major"] == {"const": 2}
    assert schemas["ErrorResponse"]["required"] == ["error", "context"]
    assert schemas["SearchRequest"]["additionalProperties"] is False
    assert schemas["LLMSearchRequest"]["additionalProperties"] is False
    assert schemas["FetchRequest"]["additionalProperties"] is False


def test_target_provider_manifest_fixture_requires_safe_static_conformance() -> None:
    fixture = _read("target_provider_manifest_v2.json")
    manifest = fixture["manifest"]
    assert fixture["contract_version"] == manifest["contract_version"] == "provider-v2"
    assert manifest["schema_version"] == 2
    assert manifest["capabilities"] == ["search"]
    assert {adapter["capability"] for adapter in manifest["adapters"]} == set(
        manifest["capabilities"]
    )
    assert "values" not in manifest["secrets"]
    assert fixture["negative_cases"]["literal_secret_value"] == "reject"
    assert fixture["negative_cases"]["export_spi_mismatch"] == "quarantine_package_only"
    assert fixture["conformance"]["deterministic_only"] is True
    assert set(fixture["conformance"]["forbids"]) >= {
        "real_network",
        "production_secret",
        "cross_provider_call",
    }
