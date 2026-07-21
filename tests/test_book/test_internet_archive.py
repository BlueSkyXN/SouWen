from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.book.internet_archive import InternetArchiveClient, _SEARCH_FIELDS
from souwen.core.exceptions import SourceUnavailableError
from souwen.search import search_books


_SEARCH_RECORD = {
    "identifier": "alice-in-catalog",
    "title": "Alice in the Catalog",
    "creator": ["Ada Author", "Bob Editor"],
    "date": "Published in 1901",
    "language": ["eng", "fra"],
    "subject": ["Catalogs", "Libraries"],
    "collection": ["gutenberg", "americana"],
    "description": "A public catalog record.",
    "rights": "Public domain in the United States",
    "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/",
}


async def test_search_uses_texts_advanced_search_without_metadata_n_plus_one(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://archive\.org/advancedsearch\.php.*"),
        json={"response": {"numFound": 1, "docs": [_SEARCH_RECORD]}},
    )

    async with InternetArchiveClient() as client:
        response = await client.search("Alice", per_page=3, page=2)

    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/advancedsearch.php"
    assert request.url.params["q"] == "mediatype:texts AND (Alice)"
    assert request.url.params.get_list("fl[]") == list(_SEARCH_FIELDS)
    assert request.url.params["rows"] == "3"
    assert request.url.params["page"] == "2"
    assert request.url.params["output"] == "json"
    assert response.total_results == 1
    assert response.page == 2
    assert response.per_page == 3

    book = response.results[0]
    assert book.source == "internet_archive"
    assert book.source_record_id == "alice-in-catalog"
    assert book.title == "Alice in the Catalog"
    assert [author.name for author in book.authors] == ["Ada Author", "Bob Editor"]
    assert book.languages == ["eng", "fra"]
    assert book.subjects == ["Catalogs", "Libraries"]
    assert book.collections == ["gutenberg", "americana"]
    assert book.first_publish_year == 1901
    assert book.description == "A public catalog record."
    assert [(identifier.scheme, identifier.value) for identifier in book.identifiers] == [
        ("source_record_id", "alice-in-catalog")
    ]
    assert book.source_url == "https://archive.org/details/alice-in-catalog"
    assert httpx_mock.get_requests() == [request]


@pytest.mark.parametrize(
    ("record", "expected_status"),
    [
        (
            {
                "identifier": "public-domain",
                "title": "Public domain catalog record",
                "licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/",
            },
            "public_domain",
        ),
        (
            {
                "identifier": "restricted",
                "title": "Restricted catalog record",
                "access-restricted": "true",
                "licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/",
            },
            "restricted",
        ),
        (
            {
                "identifier": "creative-commons",
                "title": "Creative Commons catalog record",
                "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
            },
            "open_access",
        ),
        (
            {
                "identifier": "borrow-only",
                "title": "Borrow-only catalog record",
                "loans__status": "AVAILABLE",
            },
            "borrow",
        ),
        (
            {"identifier": "unknown", "title": "No rights metadata"},
            "metadata_only",
        ),
    ],
)
def test_access_mapping_is_conservative(record: dict[str, object], expected_status: str) -> None:
    book = InternetArchiveClient._parse_record(record)

    assert book.access.status == expected_status
    assert book.access.machine_download is None
    assert book.resources == []


async def test_get_by_identifier_maps_bounded_public_file_metadata(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://archive.org/metadata/alice%20catalog",
        json={
            "metadata": {
                "identifier": "alice catalog",
                "title": "Alice catalog",
                "rights": "public domain",
                "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/",
            },
            "files": [
                {
                    "name": "Alice text.txt",
                    "format": "Text",
                    "size": "66179",
                    "source": "original",
                },
                {"name": "private.epub", "format": "EPUB", "size": "12", "private": "true"},
                {"name": "scan.pdf", "format": "Text PDF", "size": "42"},
            ],
        },
    )

    async with InternetArchiveClient() as client:
        book = await client.get_by_identifier("alice catalog", file_limit=2)

    assert book.access.status == "public_domain"
    assert len(book.resources) == 2
    text_resource, pdf_resource = book.resources
    assert text_resource.url == "https://archive.org/download/alice%20catalog/Alice%20text.txt"
    assert text_resource.relation == "file"
    assert text_resource.label == "Alice text.txt"
    assert text_resource.file_name == "Alice text.txt"
    assert text_resource.format == "Text"
    assert text_resource.media_type == "text/plain"
    assert text_resource.size_bytes == 66179
    assert text_resource.source == "internet_archive"
    assert text_resource.access.status == "public_domain"
    assert pdf_resource.file_name == "scan.pdf"
    assert pdf_resource.format == "Text PDF"
    assert pdf_resource.media_type == "application/pdf"
    assert pdf_resource.size_bytes == 42
    assert all(resource.file_name != "private.epub" for resource in book.resources)


@pytest.mark.parametrize(
    ("identifier", "file_limit"),
    [
        ("", 1),
        ("   ", 1),
        ("path/traversal", 1),
        ("valid", 0),
        ("valid", 51),
    ],
)
async def test_get_by_identifier_rejects_invalid_input_before_request(
    identifier: str, file_limit: int
) -> None:
    async with InternetArchiveClient() as client:
        with pytest.raises(ValueError):
            await client.get_by_identifier(identifier, file_limit=file_limit)


@pytest.mark.parametrize("per_page,page", [(0, 1), (101, 1), (1, 0)])
async def test_search_rejects_invalid_pagination_before_request(per_page: int, page: int) -> None:
    async with InternetArchiveClient() as client:
        with pytest.raises(ValueError):
            await client.search("catalog", per_page=per_page, page=page)


async def test_search_maps_upstream_5xx(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://archive\.org/advancedsearch\.php.*"), status_code=503
    )
    async with InternetArchiveClient() as client:
        with pytest.raises(SourceUnavailableError):
            await client.search("catalog")


async def test_search_books_dispatches_explicit_internet_archive_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(self, query: str, *, per_page: int, page: int = 1):
        assert (query, per_page, page) == ("catalog", 2, 1)
        return type(
            "Response",
            (),
            {
                "query": query,
                "source": "internet_archive",
                "total_results": 0,
                "page": page,
                "per_page": per_page,
                "results": [],
            },
        )()

    monkeypatch.setattr(InternetArchiveClient, "search", fake_search)
    responses = await search_books("catalog", sources=["internet_archive"], per_page=2)

    assert len(responses) == 1
    assert responses[0].source == "internet_archive"
