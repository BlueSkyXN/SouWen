"""OpenAPI contract tests for public server endpoints."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")


def _component_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def test_sources_endpoint_exposes_source_catalog_contract() -> None:
    """``/api/v1/sources`` must expose the formal Source Catalog response shape."""
    from souwen.server.app import app

    schema = app.openapi()
    operation = schema["paths"]["/api/v1/sources"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert response_schema["$ref"].endswith("/SourceCatalogResponse")

    components = schema["components"]["schemas"]
    response_component = components[_component_name(response_schema["$ref"])]
    response_props = response_component["properties"]
    assert set(response_props) == {"sources", "categories", "defaults"}
    assert not {"paper", "general", "wiki"} & set(response_props)

    source_ref = response_props["sources"]["items"]["$ref"]
    source_component = components[_component_name(source_ref)]
    source_props = source_component["properties"]
    assert {
        "name",
        "domain",
        "category",
        "capabilities",
        "description",
        "auth_requirement",
        "credential_fields",
        "credentials_satisfied",
        "configured_credentials",
        "risk_level",
        "stability",
        "distribution",
        "default_for",
        "available",
    } <= set(source_props)

    assert "SourcesResponse" not in components
