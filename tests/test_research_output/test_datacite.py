from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.research_output.datacite import DataCiteClient
from souwen.search import search_research_outputs


def _record(
    *,
    doi: str = "10.5281/zenodo.3723806",
    resource_type_general: str = "Dataset",
    resource_type: str | None = "Research dataset",
    publisher: object = "Zenodo",
    content_url: object = ["https://zenodo.org/records/3723806/files/data.csv"],
) -> dict:
    return {
        "id": doi,
        "type": "dois",
        "attributes": {
            "doi": doi,
            "titles": [{"title": "Climate output", "titleType": "Other"}],
            "creators": [
                {
                    "name": "Author, Ada",
                    "givenName": "Ada",
                    "familyName": "Author",
                    "nameType": "Personal",
                    "affiliation": ["Research Lab"],
                    "nameIdentifiers": [
                        {
                            "nameIdentifier": "0000-0001-0000-0001",
                            "nameIdentifierScheme": "ORCID",
                            "schemeUri": "https://orcid.org",
                        }
                    ],
                }
            ],
            "contributors": [
                {
                    "name": "Curator, Bea",
                    "contributorType": "DataCurator",
                    "affiliation": [{"name": "Repository"}],
                }
            ],
            "publisher": publisher,
            "publicationYear": 2024,
            "dates": [{"date": "2024-03-01", "dateType": "Issued"}],
            "subjects": [
                {
                    "subject": "Climate",
                    "subjectScheme": "Fields of Science",
                    "schemeUri": "https://example.test/scheme",
                }
            ],
            "descriptions": [{"description": "<p>Abstract</p>", "descriptionType": "Abstract"}],
            "fundingReferences": [
                {"funderName": "Open Fund", "awardNumber": "OA-1", "awardTitle": "Climate"}
            ],
            "types": {
                "resourceTypeGeneral": resource_type_general,
                "resourceType": resource_type,
            },
            "rightsList": [
                {
                    "rights": "Creative Commons Attribution 4.0 International",
                    "rightsUri": "https://creativecommons.org/licenses/by/4.0/legalcode",
                    "rightsIdentifier": "cc-by-4.0",
                    "rightsIdentifierScheme": "SPDX",
                },
                {"rights": "Open Access", "rightsUri": "info:eu-repo/semantics/openAccess"},
            ],
            "relatedIdentifiers": [
                {
                    "relatedIdentifier": "10.1234/related",
                    "relatedIdentifierType": "DOI",
                    "relationType": "IsSupplementTo",
                    "resourceTypeGeneral": "Text",
                }
            ],
            "geoLocations": [{"geoLocationPlace": "Earth"}],
            "identifiers": [{"identifier": "ark:/12345/example", "identifierType": "ARK"}],
            "language": "en",
            "version": "1.0",
            "url": "https://zenodo.org/records/3723806",
            "contentUrl": content_url,
        },
    }


@pytest.mark.parametrize(
    ("general", "specific"),
    [
        ("Dataset", "Research dataset"),
        ("Software", "Python software"),
        ("Text", "Presentation"),
        ("Event", "Conference"),
    ],
)
def test_normalizer_preserves_non_paper_resource_types_and_metadata(
    general: str, specific: str
) -> None:
    result = DataCiteClient._parse_record(
        _record(resource_type_general=general, resource_type=specific)
    )

    assert (result.resource_type_general, result.resource_type) == (general, specific)
    assert result.creators[0].affiliations == ["Research Lab"]
    assert result.contributors[0].contributor_type == "DataCurator"
    assert result.subjects[0].scheme == "Fields of Science"
    assert result.descriptions[0].value == "<p>Abstract</p>"
    assert result.funding_references[0].award_number == "OA-1"
    assert len(result.rights_list) == 2
    assert result.related_identifiers[0].relation_type == "IsSupplementTo"
    assert result.geo_locations == [{"geoLocationPlace": "Earth"}]
    assert [resource.relation for resource in result.resources] == ["landing_page", "content_url"]
    assert result.access.status == "metadata_only"


async def test_search_uses_documented_json_api_pagination_and_normalizes_records(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://api\.datacite\.org/dois\?.*"),
        json={
            "data": [_record()],
            "meta": {"total": 42, "page": 2},
            "links": {"next": "https://api.datacite.org/dois?page%5Bnumber%5D=3"},
        },
    )

    async with DataCiteClient() as client:
        response = await client.search("climate dataset", per_page=2, page=2)

    request = httpx_mock.get_request()
    assert request is not None
    assert dict(request.url.params) == {
        "query": "climate dataset",
        "page[size]": "2",
        "page[number]": "2",
        "sort": "relevance",
        "disable-facets": "true",
    }
    assert response.total_results == 42
    assert response.results[0].source_record_id == "10.5281/zenodo.3723806"


async def test_detail_accepts_publisher_and_affiliation_object_shapes_and_null_content_url(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://api\.datacite\.org/dois/10\.5281/zenodo\.3723806\?.*"),
        json={"data": _record(publisher={"name": "Zenodo"}, content_url=None)},
    )

    async with DataCiteClient() as client:
        result = await client.get_by_doi("10.5281/zenodo.3723806")

    assert result.publisher == "Zenodo"
    assert result.contributors[0].affiliations == ["Repository"]
    assert result.content_urls == []
    assert [item.relation for item in result.resources] == ["landing_page"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": "", "per_page": 1, "page": 1},
        {"query": "x", "per_page": 101, "page": 1},
        {"query": "x", "per_page": 1, "page": 0},
    ],
)
async def test_search_rejects_invalid_pagination_before_request(
    kwargs: dict[str, object], httpx_mock: HTTPXMock
) -> None:
    async with DataCiteClient() as client:
        with pytest.raises(ValueError):
            await client.search(**kwargs)
    assert httpx_mock.get_requests() == []


async def test_research_output_facade_dispatches_default_datacite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(self, query: str, *, per_page: int, page: int = 1):
        assert (query, per_page, page) == ("climate", 2, 1)
        return type("Response", (), {"source": "datacite", "results": []})()

    monkeypatch.setattr(DataCiteClient, "search", fake_search)
    result = await search_research_outputs("climate", per_page=2)

    assert result[0].source == "datacite"
