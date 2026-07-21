from __future__ import annotations

import pytest

pytest.importorskip("fastapi")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


def test_citation_routes_have_typed_slash_safe_query_contract(client, monkeypatch):
    from souwen.models import CitationCountResponse, CitationGraphResponse

    seen = []

    async def count(identifier):
        seen.append(("count", identifier))
        return CitationCountResponse(
            identifier={"scheme": "doi", "value": "10.1/x"},
            count=2,
            source_url="https://example.test/count",
        )

    async def incoming(identifier, *, max_edges):
        seen.append(("incoming", identifier, max_edges))
        return CitationGraphResponse(
            identifier={"scheme": "doi", "value": "10.1/x"},
            relation="citations",
            total_edges=0,
            returned_edges=0,
            source_url="https://example.test/incoming",
        )

    monkeypatch.setattr("souwen.citations.get_citation_count", count)
    monkeypatch.setattr("souwen.citations.get_incoming_citations", incoming)
    count_response = client.get("/api/v1/citations/count", params={"identifier": "doi:10.1/x"})
    incoming_response = client.get(
        "/api/v1/citations/incoming", params={"identifier": "doi:10.1/x", "max_edges": 3}
    )
    assert count_response.status_code == 200
    assert count_response.json()["count"] == 2
    assert incoming_response.status_code == 200
    assert incoming_response.json()["relation"] == "citations"
    assert seen == [("count", "doi:10.1/x"), ("incoming", "doi:10.1/x", 3)]


def test_citation_route_maps_validation_and_upstream_errors(client, monkeypatch):
    from souwen.core.exceptions import RateLimitError, SourceUnavailableError

    async def invalid(_identifier):
        raise ValueError("invalid identifier")

    monkeypatch.setattr("souwen.citations.get_citation_count", invalid)
    assert (
        client.get("/api/v1/citations/count", params={"identifier": "doi:10.1/x"}).status_code
        == 422
    )

    async def rate_limited(_identifier):
        raise RateLimitError("slow down")

    monkeypatch.setattr("souwen.citations.get_citation_count", rate_limited)
    assert (
        client.get("/api/v1/citations/count", params={"identifier": "doi:10.1/x"}).status_code
        == 429
    )

    async def unavailable(_identifier):
        raise SourceUnavailableError("upstream")

    monkeypatch.setattr("souwen.citations.get_citation_count", unavailable)
    assert (
        client.get("/api/v1/citations/count", params={"identifier": "doi:10.1/x"}).status_code
        == 502
    )


def test_openapi_exposes_typed_citation_responses():
    from souwen.server.app import app

    paths = app.openapi()["paths"]
    assert set(paths) >= {
        "/api/v1/citations/count",
        "/api/v1/citations/incoming",
        "/api/v1/citations/references",
    }
    assert paths["/api/v1/citations/count"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/CitationCountResponse")
    assert paths["/api/v1/citations/incoming"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/CitationGraphResponse")
