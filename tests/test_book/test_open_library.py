from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.book.open_library import OpenLibraryClient
from souwen.core.exceptions import SourceUnavailableError
from souwen.search import search_books


_SEARCH_PAYLOAD = {
    "numFound": 1,
    "docs": [
        {
            "key": "/works/OL123W",
            "title": "A Catalogued Book",
            "author_name": ["Ada Author"],
            "first_publish_year": 2001,
            "publisher": ["Example Press"],
            "language": ["eng"],
            "subject": ["Catalogs"],
            "isbn": ["978-0-123456-47-2", "bad-isbn"],
            "lccn": ["2001000001"],
            "oclc": ["123456"],
            "cover_i": 42,
            "ia": ["cataloguedbook0000auth"],
            "public_scan_b": False,
        }
    ],
}


async def test_search_uses_official_work_endpoint_without_edition_n_plus_one(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r"https://openlibrary\.org/search\.json.*"), json=_SEARCH_PAYLOAD
    )

    async with OpenLibraryClient() as client:
        response = await client.search("catalogued book", per_page=3, page=2)

    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/search.json"
    assert dict(request.url.params)["q"] == "catalogued book"
    assert dict(request.url.params)["limit"] == "3"
    assert dict(request.url.params)["page"] == "2"
    assert response.total_results == 1
    assert response.page == 2
    book = response.results[0]
    assert book.source_record_id == "OL123W"
    assert book.source_url == "https://openlibrary.org/works/OL123W"
    assert [author.name for author in book.authors] == ["Ada Author"]
    assert {(item.scheme, item.value) for item in book.identifiers} == {
        ("olid", "OL123W"),
        ("isbn13", "978-0-123456-47-2"),
        ("lccn", "2001000001"),
        ("oclc", "123456"),
    }
    assert book.access.status == "metadata_only"
    archive = next(item for item in book.resources if item.source == "internet_archive")
    assert archive.url == "https://archive.org/details/cataloguedbook0000auth"
    assert archive.access.status == "unknown"
    assert archive.access.machine_download is None
    assert httpx_mock.get_requests() == [request]


async def test_get_work_fetches_only_a_bounded_edition_sample(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://openlibrary.org/works/OL123W.json",
        json={
            "title": "A Work",
            "description": {"value": "Work-level description"},
            "subjects": ["Libraries"],
            "covers": [100],
        },
    )
    httpx_mock.add_response(
        url="https://openlibrary.org/works/OL123W/editions.json?limit=2",
        json={
            "entries": [
                {
                    "key": "/books/OL456M",
                    "publishers": ["Example Press"],
                    "publish_date": "2002",
                    "physical_format": "Hardcover",
                    "languages": [{"key": "/languages/eng"}],
                    "number_of_pages": 123,
                    "isbn": ["0123456789"],
                    "covers": [101],
                }
            ]
        },
    )

    async with OpenLibraryClient() as client:
        book = await client.get_by_work_id("/works/OL123W", edition_limit=2)

    assert book.title == "A Work"
    assert book.description == "Work-level description"
    assert len(book.editions) == 1
    edition = book.editions[0]
    assert edition.olid == "OL456M"
    assert edition.formats == ["Hardcover"]
    assert edition.languages == ["eng"]
    assert edition.page_count == 123
    assert {(item.scheme, item.value) for item in edition.identifiers} >= {
        ("olid", "OL456M"),
        ("isbn10", "0123456789"),
    }
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.parametrize("per_page,page", [(0, 1), (101, 1), (1, 0)])
async def test_search_rejects_invalid_pagination_before_request(per_page: int, page: int):
    async with OpenLibraryClient() as client:
        with pytest.raises(ValueError):
            await client.search("book", per_page=per_page, page=page)


async def test_search_maps_upstream_5xx(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r"https://openlibrary\.org/search\.json.*"), status_code=503
    )
    async with OpenLibraryClient() as client:
        with pytest.raises(SourceUnavailableError):
            await client.search("book")


async def test_search_books_dispatches_explicit_open_library_source(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_search(self, query: str, *, per_page: int, page: int = 1):
        assert (query, per_page, page) == ("book", 2, 1)
        return type(
            "Response",
            (),
            {
                "query": query,
                "source": "open_library",
                "total_results": 0,
                "page": 1,
                "per_page": per_page,
                "results": [],
            },
        )()

    monkeypatch.setattr(OpenLibraryClient, "search", fake_search)
    responses = await search_books("book", sources=["open_library"], per_page=2)
    assert len(responses) == 1
    assert responses[0].source == "open_library"
