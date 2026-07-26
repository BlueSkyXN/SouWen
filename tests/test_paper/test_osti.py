from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.common_runtime.provider_support.exceptions import (
    NotFoundError,
    ParseError,
    SourceUnavailableError,
)
from souwen.providers.runtime_clients.paper.osti import OstiClient


OSTI_RECORD = {
    "osti_id": "3012392",
    "doi": "10.1234/example.1",
    "title": "Official OSTI record",
    "authors": ["Doe, Jane", {"first_name": "John", "last_name": "Smith"}],
    "publication_date": "2025-03-15",
    "product_type": "Technical Report",
    "description": "A source-provided abstract.",
    "subjects": ["Machine learning"],
    "sponsor_orgs": ["U.S. Department of Energy"],
    "research_orgs": ["Example Laboratory"],
    "links": [
        {"rel": "citation", "href": "https://www.osti.gov/biblio/3012392"},
        {"rel": "fulltext", "href": "https://www.osti.gov/servlets/purl/3012392"},
    ],
}


async def test_search_uses_official_q_parameter_and_normalizes_records(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r"https://www\.osti\.gov/api/v1/records.*"),
        headers={"x-total-count": "4148752"},
        json=[OSTI_RECORD],
    )

    async with OstiClient() as client:
        response = await client.search("machine learning", rows=5, page=2)

    request = httpx_mock.get_request()
    assert request is not None
    assert dict(request.url.params) == {"q": "machine learning", "rows": "5", "page": "2"}
    assert response.source == "osti"
    assert response.total_results == 4_148_752
    assert response.page == 2
    assert response.per_page == 5
    paper = response.results[0]
    assert paper.source == "osti"
    assert paper.title == "Official OSTI record"
    assert [author.name for author in paper.authors] == ["Doe, Jane", "John Smith"]
    assert paper.abstract == "A source-provided abstract."
    assert paper.doi == "10.1234/example.1"
    assert paper.year == 2025
    assert paper.publication_date.isoformat() == "2025-03-15"
    assert paper.source_url == "https://www.osti.gov/biblio/3012392"
    assert paper.pdf_url is None
    assert paper.open_access_url is None
    assert paper.raw == {
        "osti_id": "3012392",
        "product_type": "Technical Report",
        "subjects": ["Machine learning"],
        "sponsor_orgs": ["U.S. Department of Energy"],
        "research_orgs": ["Example Laboratory"],
        "resource_links": OSTI_RECORD["links"],
    }


async def test_detail_uses_official_record_path_and_normalizes_array_response(
    httpx_mock: HTTPXMock,
):
    httpx_mock.add_response(
        url="https://www.osti.gov/api/v1/records/3012392",
        json=[OSTI_RECORD],
    )

    async with OstiClient() as client:
        result = await client.get_by_id(" 3012392 ")

    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/api/v1/records/3012392"
    assert result.source == "osti"
    assert result.raw["osti_id"] == "3012392"


@pytest.mark.parametrize(("rows", "page", "message"), [(0, 1, "rows"), (1, 0, "page")])
async def test_search_rejects_invalid_pagination_before_request(rows: int, page: int, message: str):
    async with OstiClient() as client:
        with pytest.raises(ValueError, match=message):
            await client.search("machine learning", rows=rows, page=page)


@pytest.mark.parametrize("osti_id", [" ", "https://www.osti.gov/api/v1/records/3012392", "3012/x"])
async def test_detail_rejects_non_record_id_before_request(osti_id: str):
    async with OstiClient() as client:
        with pytest.raises(ValueError, match="osti_id"):
            await client.get_by_id(osti_id)


async def test_detail_maps_missing_or_empty_record_to_not_found(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="https://www.osti.gov/api/v1/records/9999999", status_code=404)
    httpx_mock.add_response(url="https://www.osti.gov/api/v1/records/9999998", json=[])

    async with OstiClient() as client:
        with pytest.raises(NotFoundError):
            await client.get_by_id("9999999")
        with pytest.raises(NotFoundError):
            await client.get_by_id("9999998")


async def test_search_rejects_non_array_upstream_payload(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r"https://www\.osti\.gov/api/v1/records.*"), json={"records": []}
    )

    async with OstiClient() as client:
        with pytest.raises(ParseError, match="数组"):
            await client.search("machine learning")


async def test_search_propagates_upstream_server_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r"https://www\.osti\.gov/api/v1/records.*"),
        status_code=502,
        text="bad gateway",
    )

    async with OstiClient() as client:
        with pytest.raises(SourceUnavailableError):
            await client.search("machine learning")
