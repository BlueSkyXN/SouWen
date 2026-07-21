from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")


@pytest.fixture(autouse=True)
def isolated_search_limiter(monkeypatch):
    from souwen.server import limiter as limiter_mod

    monkeypatch.setattr(
        limiter_mod,
        "_search_limiter",
        limiter_mod.InMemoryRateLimiter(max_requests=60, window_seconds=60),
    )


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


def test_research_output_route_uses_registry_backed_public_facade(client, monkeypatch):
    from souwen.models import ResearchOutputResult, SearchResponse

    async def fake_search(query, *, sources=None, per_page=10):
        assert (query, sources, per_page) == ("climate", None, 2)
        return [
            SearchResponse(
                query=query,
                source="datacite",
                total_results=1,
                results=[
                    ResearchOutputResult(
                        source="datacite",
                        source_record_id="10.5281/zenodo.3723806",
                        title="Climate dataset",
                        resource_type_general="Dataset",
                        resource_type="Research dataset",
                        source_url="https://doi.org/10.5281/zenodo.3723806",
                    )
                ],
            )
        ]

    search_module = importlib.import_module("souwen.search")
    monkeypatch.setattr(search_module, "search_research_outputs", fake_search)
    response = client.get(
        "/api/v1/search/research-output", params={"q": " climate ", "per_page": 2}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == ["datacite"]
    assert payload["meta"]["succeeded"] == ["datacite"]
    item = payload["results"][0]["results"][0]
    assert (item["resource_type_general"], item["resource_type"]) == (
        "Dataset",
        "Research dataset",
    )


def test_research_output_route_has_public_auth_and_openapi_contract(client):
    assert client.get("/api/v1/search/research-output", params={"q": ""}).status_code == 422
    from souwen.server.app import app

    schema = app.openapi()["paths"]["/api/v1/search/research-output"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert schema["$ref"].endswith("/SearchResearchOutputResponse")
