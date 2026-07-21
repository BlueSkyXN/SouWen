from __future__ import annotations

import json
import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.core.exceptions import NotFoundError, ParseError
from souwen.research_output.figshare import FigshareClient
from souwen.search import search_research_outputs


def _article(
    *,
    article_id: int = 33046703,
    defined_type_name: str = "dataset",
    include_files: bool = True,
    include_license: bool = True,
) -> dict:
    record: dict = {
        "id": article_id,
        "title": "Climate output",
        "doi": f"10.6084/m9.figshare.{article_id}.v1",
        "defined_type": 3,
        "defined_type_name": defined_type_name,
        "url_public_api": f"https://api.figshare.com/v2/articles/{article_id}",
        "url_public_html": f"https://figshare.com/articles/dataset/climate/{article_id}",
        "authors": [
            {
                "id": 123,
                "full_name": "Ada Author",
                "first_name": "Ada",
                "last_name": "Author",
                "orcid_id": "0000-0001-0000-0001",
            }
        ],
        "categories": [{"id": 7, "title": "Climate science"}],
        "tags": ["climate", "dataset"],
        "description": "<p>Public output metadata.</p>",
        "published_date": "2025-01-02T03:04:05Z",
        "created_date": "2025-01-01T00:00:00Z",
        "modified_date": "2025-01-03T00:00:00Z",
        "funding_list": [{"id": 456, "funder_name": "Open Fund", "grant_code": "CLIMATE-1"}],
    }
    if include_license:
        record["license"] = {
            "name": "CC BY 4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
        }
    if include_files:
        record["files"] = [
            {
                "id": 1,
                "name": "data.csv",
                "size": 42,
                "is_link_only": False,
                "download_url": "https://ndownloader.figshare.com/files/1",
                "mimetype": "text/csv",
                "supplied_md5": "unused-source-metadata",
            },
            {
                "id": 2,
                "name": "external-data.txt",
                "size": 99,
                "is_link_only": True,
                "download_url": "https://ndownloader.figshare.com/files/2",
                "mimetype": "text/plain",
                "computed_md5": "unused-source-metadata",
            },
        ]
    return record


@pytest.mark.parametrize(
    ("defined_type_name", "expected_general"),
    [("dataset", "Dataset"), ("software", "Software"), ("figure", "Image")],
)
def test_normalizer_preserves_figshare_article_type_license_and_declared_files(
    defined_type_name: str, expected_general: str
) -> None:
    result = FigshareClient._parse_record(_article(defined_type_name=defined_type_name))

    assert (result.resource_type_general, result.resource_type) == (
        expected_general,
        defined_type_name,
    )
    assert [(item.scheme, item.value) for item in result.identifiers] == [
        ("doi", "10.6084/m9.figshare.33046703.v1"),
        ("figshare_article_id", "33046703"),
    ]
    assert result.creators[0].name == "Ada Author"
    assert result.creators[0].identifiers[0].scheme == "orcid"
    assert [item.subject for item in result.subjects] == [
        "Climate science",
        "climate",
        "dataset",
    ]
    assert result.rights_list[0].rights == "CC BY 4.0"
    assert result.access.status == "metadata_only"
    files = [resource for resource in result.resources if resource.relation == "declared_file_url"]
    assert [(item.file_name, item.size_bytes, item.is_link_only) for item in files] == [
        ("data.csv", 42, False),
        ("external-data.txt", 99, True),
    ]
    assert all(item.access.machine_download is None for item in files)
    assert all("does not follow" in (item.access.notes or "") for item in files)


def test_normalizer_accepts_missing_license_and_files_without_claiming_access() -> None:
    result = FigshareClient._parse_record(_article(include_files=False, include_license=False))

    assert result.rights_list == []
    assert result.access.rights is None
    assert [item.relation for item in result.resources] == ["landing_page"]


async def test_search_posts_documented_page_and_page_size_without_detail_fanout(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.figshare.com/v2/articles/search",
        json=[_article(include_files=False)],
    )

    async with FigshareClient() as client:
        response = await client.search("climate dataset", page_size=2, page=3)

    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert json.loads(request.content) == {
        "search_for": "climate dataset",
        "page": 3,
        "page_size": 2,
    }
    assert response.total_results is None
    assert response.page == 3
    assert response.per_page == 2
    assert response.results[0].resources[0].relation == "landing_page"
    assert len(httpx_mock.get_requests()) == 1


async def test_get_by_id_only_requests_public_detail_and_maps_404(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://api.figshare.com/v2/articles/33046703",
        json=_article(),
    )

    async with FigshareClient() as client:
        result = await client.get_by_id("33046703")

    assert result.source_record_id == "33046703"
    assert len([item for item in result.resources if item.relation == "declared_file_url"]) == 2
    assert [request.url.path for request in httpx_mock.get_requests()] == ["/v2/articles/33046703"]

    httpx_mock.add_response(
        method="GET",
        url="https://api.figshare.com/v2/articles/404",
        status_code=404,
        json={"message": "Not found"},
    )
    async with FigshareClient() as client:
        with pytest.raises(NotFoundError, match="404"):
            await client.get_by_id(404)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": "", "page_size": 1, "page": 1},
        {"query": "x", "page_size": 101, "page": 1},
        {"query": "x", "page_size": 1, "page": 0},
    ],
)
async def test_search_rejects_invalid_pagination_before_request(
    kwargs: dict[str, object], httpx_mock: HTTPXMock
) -> None:
    async with FigshareClient() as client:
        with pytest.raises(ValueError):
            await client.search(**kwargs)
    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("article_id", ["", "a", "1/2", 0, -1, True])
async def test_detail_rejects_non_public_article_id_before_request(
    article_id: object, httpx_mock: HTTPXMock
) -> None:
    async with FigshareClient() as client:
        with pytest.raises(ValueError):
            await client.get_by_id(article_id)  # type: ignore[arg-type]
    assert httpx_mock.get_requests() == []


async def test_search_rejects_malformed_envelope_and_skips_malformed_records(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r"https://api\.figshare\.com/v2/articles/search"),
        json={"items": []},
    )
    async with FigshareClient() as client:
        with pytest.raises(ParseError, match="不是列表"):
            await client.search("climate")

    httpx_mock.add_response(
        method="POST",
        url=re.compile(r"https://api\.figshare\.com/v2/articles/search"),
        json=[{"id": "bad"}, _article(include_files=False)],
    )
    async with FigshareClient() as client:
        response = await client.search("climate")
    assert [item.source_record_id for item in response.results] == ["33046703"]


async def test_research_output_facade_dispatches_explicit_figshare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(self, query: str, *, page_size: int, page: int = 1):
        assert (query, page_size, page) == ("climate", 2, 1)
        return type("Response", (), {"source": "figshare", "results": []})()

    monkeypatch.setattr(FigshareClient, "search", fake_search)
    result = await search_research_outputs("climate", sources=["figshare"], per_page=2)

    assert result[0].source == "figshare"
