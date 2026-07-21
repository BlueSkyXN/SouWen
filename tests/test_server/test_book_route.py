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


def test_book_route_uses_registry_backed_public_facade(client, monkeypatch):
    from souwen.models import BookResult, SearchResponse

    async def fake_search(query, *, sources=None, per_page=10):
        assert (query, sources, per_page) == ("catalog", None, 2)
        return [
            SearchResponse(
                query=query,
                source="open_library",
                total_results=1,
                results=[
                    BookResult(
                        source="open_library",
                        source_record_id="OL1W",
                        title="Catalog",
                        source_url="https://openlibrary.org/works/OL1W",
                    )
                ],
            )
        ]

    search_module = importlib.import_module("souwen.search")
    monkeypatch.setattr(search_module, "search_books", fake_search)
    response = client.get("/api/v1/search/book", params={"q": " catalog ", "per_page": 2})
    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == ["open_library"]
    assert payload["meta"]["succeeded"] == ["open_library"]
    assert payload["results"][0]["results"][0]["source_record_id"] == "OL1W"


def test_book_route_has_public_auth_and_openapi_contract(client):
    assert client.get("/api/v1/search/book", params={"q": ""}).status_code == 422
    from souwen.server.app import app

    schema = app.openapi()["paths"]["/api/v1/search/book"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert schema["$ref"].endswith("/SearchBookResponse")


def test_explicit_uninitialized_gutenberg_returns_safe_503(client, monkeypatch, tmp_path):
    from souwen.core.exceptions import LocalCatalogUnavailableError

    async def unavailable(*_args, **_kwargs):
        raise LocalCatalogUnavailableError(f"local catalog is not initialized: {tmp_path}")

    search_module = importlib.import_module("souwen.search")
    monkeypatch.setattr(search_module, "search_books", unavailable)

    response = client.get("/api/v1/search/book", params={"q": "Alice", "sources": "gutenberg"})

    assert response.status_code == 503
    assert "souwen catalog import gutenberg <rdf-input>" in response.json()["detail"]
    assert str(tmp_path) not in response.text
