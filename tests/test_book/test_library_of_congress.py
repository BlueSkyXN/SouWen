from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.book.library_of_congress import LibraryOfCongressClient
from souwen.core.exceptions import NotFoundError, SourceUnavailableError
from souwen.search import search_books


_RECORD = {
    "id": "http://www.loc.gov/item/2024000001/",
    "title": "A Library Catalog Book",
    "date": "2024-01-01",
    "contributors": ["Ada Author"],
    "subject": ["Libraries"],
    "language": ["english"],
    "number_lccn": ["2024000001"],
    "number_isbn": ["978-0-123456-47-2"],
    "location": ["Washington, D.C."],
    "rights": ["No known restrictions"],
    "access_restricted": False,
    "resources": [{"caption": "digital file", "url": "https://www.loc.gov/resource/example.1/"}],
}


async def test_search_uses_official_json_pagination_and_keeps_resources_conservative(
    httpx_mock: HTTPXMock,
):
    httpx_mock.add_response(
        url=re.compile(r"https://www\.loc\.gov/books/.*"),
        json={"pagination": {"total": 1}, "results": [_RECORD]},
    )
    async with LibraryOfCongressClient() as client:
        response = await client.search("catalog", per_page=2, page=3)
    request = httpx_mock.get_request()
    assert request is not None
    assert dict(request.url.params) == {"q": "catalog", "fo": "json", "c": "2", "sp": "3"}
    book = response.results[0]
    assert book.source_record_id == "2024000001"
    assert {(x.scheme, x.value) for x in book.identifiers} >= {
        ("lccn", "2024000001"),
        ("isbn13", "978-0-123456-47-2"),
    }
    assert book.resources[0].url == "https://www.loc.gov/resource/example.1/"
    assert book.access.status == "metadata_only"
    assert book.access.machine_download is None


async def test_detail_reads_item_envelope_and_restricted_access(httpx_mock: HTTPXMock):
    record = {**_RECORD, "access_restricted": True, "resources": []}
    httpx_mock.add_response(
        url="https://www.loc.gov/item/2024000001/?fo=json", json={"item": record}
    )
    async with LibraryOfCongressClient() as client:
        book = await client.get_by_id("2024000001")
    assert book.access.status == "restricted"
    assert book.source_url == "https://www.loc.gov/item/2024000001/"


@pytest.mark.parametrize("record_id", ["", " ", "bad/path"])
async def test_detail_rejects_invalid_id_before_request(record_id: str):
    async with LibraryOfCongressClient() as client:
        with pytest.raises(ValueError):
            await client.get_by_id(record_id)


async def test_detail_missing_item_is_not_found(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="https://www.loc.gov/item/2024000001/?fo=json", json={})
    async with LibraryOfCongressClient() as client:
        with pytest.raises(NotFoundError):
            await client.get_by_id("2024000001")


async def test_search_maps_5xx(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=re.compile(r"https://www\.loc\.gov/books/.*"), status_code=503)
    async with LibraryOfCongressClient() as client:
        with pytest.raises(SourceUnavailableError):
            await client.search("catalog")


async def test_registry_dispatches_explicit_loc(monkeypatch: pytest.MonkeyPatch):
    async def fake(self, query: str, *, per_page: int, page: int = 1):
        return type("Response", (), {"source": "library_of_congress", "results": []})()

    monkeypatch.setattr(LibraryOfCongressClient, "search", fake)
    assert (await search_books("catalog", sources=["library_of_congress"], per_page=2))[
        0
    ].source == "library_of_congress"
