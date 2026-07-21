from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.core.exceptions import NotFoundError, ParseError, RateLimitError
from souwen.paper.opencitations import OpenCitationsClient

IDENTIFIER = "doi:10.1038/nphys1170"
EDGE = {
    "oci": "06602410619-06303726193",
    "citing": "omid:br/06602410619 doi:10.1007/s11467-011-0206-z openalex:W2006217484",
    "cited": "omid:br/06303726193 doi:10.1038/nphys1170 openalex:W4289253527",
    "creation": "2012-05-04",
    "timespan": "P3Y4M",
    "journal_sc": "no",
    "author_sc": "yes",
}


@pytest.mark.parametrize(
    ("value", "canonical"),
    [
        ("10.1038/NPHYS1170", IDENTIFIER),
        ("DOI:10.1038/NPHYS1170", IDENTIFIER),
        ("https://doi.org/10.1038/NPHYS1170", IDENTIFIER),
        ("pmid:33817056", "pmid:33817056"),
        ("omid:br/06180334099", "omid:br/06180334099"),
    ],
)
def test_normalize_identifier(value: str, canonical: str) -> None:
    assert OpenCitationsClient.normalize_identifier(value).canonical == canonical


@pytest.mark.parametrize("value", ["", "not-a-doi", "openalex:W1", "pmid:not-a-number"])
def test_normalize_identifier_rejects_unknown_or_malformed_values(value: str) -> None:
    with pytest.raises(ValueError):
        OpenCitationsClient.normalize_identifier(value)


async def test_count_uses_encoded_canonical_identifier_and_parses_string_count(
    httpx_mock: HTTPXMock,
):
    httpx_mock.add_response(
        url=re.compile(
            r"https://api\.opencitations\.net/index/v2/citation-count/doi:10\.1038%2Fnphys1170"
        ),
        json=[{"count": "9"}],
    )
    async with OpenCitationsClient() as client:
        response = await client.citation_count("https://doi.org/10.1038/NPHYS1170")
    assert response.identifier.canonical == IDENTIFIER
    assert response.count == 9
    assert response.rights == "CC0-1.0"
    assert response.source == "opencitations"


async def test_graph_preserves_all_identifiers_and_marks_local_truncation(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(
            r"https://api\.opencitations\.net/index/v2/citations/doi:10\.1038%2Fnphys1170"
        ),
        json=[EDGE, {**EDGE, "oci": "other"}],
    )
    async with OpenCitationsClient() as client:
        response = await client.citations(IDENTIFIER, max_edges=1)
    assert response.relation == "citations"
    assert response.total_edges == 2
    assert response.returned_edges == 1
    assert response.truncated is True
    edge = response.edges[0]
    assert edge.creation == "2012-05-04"
    assert edge.timespan == "P3Y4M"
    assert edge.author_self_citation is True
    assert edge.journal_self_citation is False
    assert [item.canonical for item in edge.citing] == [
        "omid:br/06602410619",
        "doi:10.1007/s11467-011-0206-z",
        "openalex:W2006217484",
    ]


async def test_empty_valid_graph_is_normal_business_result(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r"https://api\.opencitations\.net/index/v2/references/pmid:999999"),
        json=[],
    )
    async with OpenCitationsClient() as client:
        response = await client.references("pmid:999999")
    assert response.total_edges == 0
    assert response.edges == []
    assert response.truncated is False


async def test_client_maps_http_and_parse_errors(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r"https://api\.opencitations\.net/index/v2/citation-count/.*"),
        status_code=404,
    )
    httpx_mock.add_response(
        url=re.compile(r"https://api\.opencitations\.net/index/v2/citations/.*"), status_code=429
    )
    httpx_mock.add_response(
        url=re.compile(r"https://api\.opencitations\.net/index/v2/references/.*"), json={}
    )
    async with OpenCitationsClient() as client:
        with pytest.raises(NotFoundError):
            await client.citation_count(IDENTIFIER)
        with pytest.raises(RateLimitError):
            await client.citations(IDENTIFIER)
        with pytest.raises(ParseError):
            await client.references(IDENTIFIER)


async def test_registry_dispatches_each_namespaced_capability(monkeypatch: pytest.MonkeyPatch):
    from souwen.models import CitationCountResponse, CitationGraphResponse
    from souwen.search import search_by_capability

    async def count(self, identifier):
        return CitationCountResponse(
            identifier=OpenCitationsClient.normalize_identifier(identifier),
            count=1,
            source_url="https://example.test/count",
        )

    async def graph(self, identifier, max_edges=100):
        return CitationGraphResponse(
            identifier=OpenCitationsClient.normalize_identifier(identifier),
            relation="citations",
            total_edges=0,
            returned_edges=0,
            source_url="https://example.test/graph",
        )

    monkeypatch.setattr(OpenCitationsClient, "citation_count", count)
    monkeypatch.setattr(OpenCitationsClient, "citations", graph)
    response = await search_by_capability(
        IDENTIFIER, "opencitations:citation_count", sources=["opencitations"], identifier=IDENTIFIER
    )
    graph_response = await search_by_capability(
        IDENTIFIER,
        "opencitations:citations",
        sources=["opencitations"],
        identifier=IDENTIFIER,
        max_edges=2,
    )
    assert response[0].count == 1
    assert graph_response[0].relation == "citations"
