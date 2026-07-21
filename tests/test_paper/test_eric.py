from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.core.exceptions import SourceUnavailableError
from souwen.models import SearchResponse
from souwen.paper.eric import EricClient
from souwen.search import search_papers


ERIC_RESPONSE = {
    "response": {
        "numFound": 2,
        "start": 0,
        "docs": [
            {
                "id": "ED123456",
                "title": "Educational Research Record",
                "author": ["Doe, Jane", "Smith, John"],
                "description": "A complete ERIC abstract.",
                "publicationdateyear": 2024,
                "publicationtype": ["Reports - Research"],
                "subject": ["Education", "Research"],
                "isbn": ["9780000000001"],
                "issn": ["1234-5678"],
                "language": ["English"],
                "peerreviewed": "T",
                "publisher": "Example Institute",
                "sourceid": "Example Journal, v1 n2",
                "source": "Example Journal",
                "url": "https://publisher.example/record",
                "e_fulltextauth": "1",
            }
        ],
    }
}


async def test_search_uses_official_params_and_normalizes_document(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r"https://api\.ies\.ed\.gov/eric/.*"),
        json=ERIC_RESPONSE,
    )

    async with EricClient() as client:
        response = await client.search("education research", rows=5, start=10)

    request = httpx_mock.get_request()
    assert request is not None
    assert dict(request.url.params) == {
        "search": "education research",
        "format": "json",
        "start": "10",
        "rows": "5",
    }
    assert response.source == "eric"
    assert response.total_results == 2
    assert response.page == 3
    assert response.per_page == 5
    paper = response.results[0]
    assert paper.title == "Educational Research Record"
    assert [author.name for author in paper.authors] == ["Doe, Jane", "Smith, John"]
    assert paper.abstract == "A complete ERIC abstract."
    assert paper.year == 2024
    assert paper.doi is None
    assert paper.journal == "Example Journal"
    assert paper.source_url == "https://eric.ed.gov/?id=ED123456"
    assert paper.pdf_url == "https://files.eric.ed.gov/fulltext/ED123456.pdf"
    assert paper.raw["eric_id"] == "ED123456"
    assert paper.raw["publication_types"] == ["Reports - Research"]
    assert paper.raw["external_url"] == "https://publisher.example/record"
    assert paper.raw["fulltext_authorized"] is True


def test_parse_record_keeps_missing_metadata_unknown_and_does_not_guess_pdf_or_doi() -> None:
    paper = EricClient._parse_record(
        {
            "id": "EJ1",
            "title": "Minimal record",
            "author": "Solo Author",
            "publicationdateyear": "not-a-year",
            "e_fulltextauth": "1",
            "url": "https://publisher.example/minimal",
        }
    )

    assert [author.name for author in paper.authors] == ["Solo Author"]
    assert paper.abstract is None
    assert paper.year is None
    assert paper.doi is None
    assert paper.pdf_url is None
    assert paper.source_url == "https://eric.ed.gov/?id=EJ1"
    assert paper.raw["fulltext_authorized"] is True


@pytest.mark.parametrize(
    ("rows", "start", "message"), [(0, 0, "rows"), (2_001, 0, "rows"), (1, -1, "start")]
)
async def test_search_rejects_invalid_pagination_before_request(
    rows: int, start: int, message: str
):
    async with EricClient() as client:
        with pytest.raises(ValueError, match=message):
            await client.search("education", rows=rows, start=start)


async def test_search_propagates_upstream_server_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r"https://api\.ies\.ed\.gov/eric/.*"),
        status_code=502,
        text="bad gateway",
    )

    async with EricClient() as client:
        with pytest.raises(SourceUnavailableError):
            await client.search("education")


async def test_search_papers_dispatches_explicit_eric_source(monkeypatch: pytest.MonkeyPatch):
    async def fake_search(self, query: str, *, rows: int, start: int = 0) -> SearchResponse:
        assert query == "education"
        assert rows == 2
        assert start == 0
        return SearchResponse(
            query=query,
            source="eric",
            total_results=1,
            per_page=rows,
            results=[
                EricClient._parse_record({"id": "ED1", "title": "Registry-dispatched ERIC record"})
            ],
        )

    monkeypatch.setattr(EricClient, "search", fake_search)

    responses = await search_papers("education", sources=["eric"], per_page=2)

    assert len(responses) == 1
    assert responses[0].source == "eric"
    assert responses[0].results[0].source == "eric"
