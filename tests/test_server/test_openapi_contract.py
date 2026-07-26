"""Target-only host OpenAPI contract."""

from __future__ import annotations

from souwen.server.app import app


TARGET_PATHS = {
    "/api/v1/search",
    "/api/v1/llm-search",
    "/api/v1/fetch",
    "/api/v1/providers",
    "/health",
    "/healthz",
    "/readiness",
    "/readyz",
}


def test_host_openapi_is_exact_target_contract() -> None:
    schema = app.openapi()
    assert set(schema["paths"]) == TARGET_PATHS
    assert schema["x-souwen-api-major"] == 2
    assert schema["x-souwen-rollout-mode"] == "target"
    assert schema["x-souwen-contract-stage"] == "target_only"
    assert schema["components"]["headers"]["X-SouWen-Rollout-Mode"]["schema"] == {"const": "target"}


def test_target_data_operations_use_generated_canonical_models() -> None:
    schema = app.openapi()
    expected = {
        "/api/v1/search": ("SearchRequest", "SearchPage"),
        "/api/v1/llm-search": ("LLMSearchRequest", "LLMSearchResult"),
        "/api/v1/fetch": ("FetchRequest", "FetchBatch"),
    }
    for path, (request_model, response_model) in expected.items():
        operation = schema["paths"][path]["post"]
        request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ]
        assert request_ref.endswith(f"/{request_model}")
        assert response_ref.endswith(f"/{response_model}")
        assert operation["security"] == [{"UserToken": []}]


def test_probe_aliases_are_frozen_2x_aliases() -> None:
    paths = app.openapi()["paths"]
    assert paths["/health"]["get"]["x-souwen-alias-of"] == "/healthz"
    assert paths["/readiness"]["get"]["x-souwen-alias-of"] == "/readyz"
    assert paths["/health"]["get"]["operationId"] == "healthAlias"
    assert paths["/readiness"]["get"]["operationId"] == "readinessAlias"


def test_retired_product_routes_are_absent() -> None:
    paths = app.openapi()["paths"]
    retired = {
        "/api/v1/sources",
        "/api/v1/search/paper",
        "/api/v1/search/book",
        "/api/v1/search/web/enriched",
        "/api/v1/citations/count",
        "/api/v1/bilibili/search",
        "/api/v1/admin/warp",
        "/api/v1/admin/proxy",
        "/api/v1/admin/sources/config",
    }
    assert retired.isdisjoint(paths)
