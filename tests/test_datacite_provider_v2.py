"""Deterministic Provider v2 checks for DataCite research-output Search."""

from __future__ import annotations

import pytest

from souwen.providers.runtime_clients.models import (
    ResearchContributor,
    ResearchOutputIdentifier,
    ResearchOutputResult,
    ResourceAccess,
    ResourceLink,
    SearchResponse,
)
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.datacite import (
    DATACITE_PROVIDER_MANIFEST,
    DATACITE_PROVIDER_SPEC,
    DataCiteSearchProvider,
)


class _Client:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, int, int]] = []
        self.closed = 0

    async def search(self, query: str, per_page: int = 10, page: int = 1) -> SearchResponse:
        self.calls.append((query, per_page, page))
        return self.response

    async def close(self) -> None:
        self.closed += 1


def _result(**overrides: object) -> ResearchOutputResult:
    values: dict[str, object] = {
        "source": "datacite",
        "source_record_id": "10.5281/zenodo.3723806",
        "title": "Climate data",
        "creators": [ResearchContributor(name="Ada Author")],
        "publication_year": 2024,
        "resource_type_general": "Dataset",
        "resource_type": "Research dataset",
        "language": "en",
        "identifiers": [
            ResearchOutputIdentifier(scheme="doi", value="10.5281/zenodo.3723806"),
            ResearchOutputIdentifier(scheme="ark", value="ark:/12345/example"),
        ],
        "access": ResourceAccess(status="open_access"),
        "resources": [
            ResourceLink(
                url="https://zenodo.org/records/3723806/files/data.csv",
                relation="content_url",
                source="datacite",
                access=ResourceAccess(status="metadata_only"),
            )
        ],
        "source_url": "https://doi.org/10.5281/zenodo.3723806",
    }
    values.update(overrides)
    return ResearchOutputResult(**values)


def _response(
    *items: ResearchOutputResult, total: int | None = None, limit: int = 3
) -> SearchResponse:
    return SearchResponse(
        query="climate",
        source="datacite",
        total_results=len(items) if total is None else total,
        page=1,
        per_page=limit,
        results=list(items),
    )


def _request() -> SearchRequest:
    return SearchRequest(
        query="climate",
        domains=("research_output",),
        page=SearchPageRequest(limit=3),
    )


@pytest.mark.asyncio
async def test_datacite_projects_only_safe_canonical_research_output_fields() -> None:
    client = _Client(_response(_result(), limit=3))
    page = await DataCiteSearchProvider(client).search(
        _request(), RequestContext(request_id="datacite"), ExecutionContext.with_timeout(1)
    )

    assert client.calls == [("climate", 3, 1)]
    item = page.items[0]
    assert item.id == "datacite:10.5281/zenodo.3723806"
    assert str(item.url) == "https://doi.org/10.5281/zenodo.3723806"
    assert item.attributes is not None
    assert item.attributes.year == 2024
    assert item.attributes.authors == ("Ada Author",)
    assert item.attributes.resource_type == "Dataset"
    assert item.attributes.language == "en"
    assert item.attributes.open_access is True
    assert {(value.scheme, value.value) for value in item.attributes.identifiers} == {
        ("datacite", "10.5281/zenodo.3723806"),
        ("doi", "10.5281/zenodo.3723806"),
        ("ark", "ark:/12345/example"),
    }
    assert "resources" not in item.model_dump()
    assert "raw" not in item.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        SearchResponse(query="climate", source="figshare", page=1, per_page=3, results=[]),
        _response(_result(source="figshare"), limit=3),
        _response(_result(title=""), limit=3),
        _response(_result(source_url="ftp://example.test/record"), limit=3),
        _response(_result(), total=-1, limit=3),
        _response(_result(), limit=2),
    ],
)
async def test_datacite_rejects_invalid_legacy_projection(response: SearchResponse) -> None:
    with pytest.raises(ProviderError) as error:
        await DataCiteSearchProvider(_Client(response)).search(
            _request(), RequestContext(request_id="invalid"), ExecutionContext.with_timeout(1)
        )
    assert error.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


@pytest.mark.asyncio
async def test_datacite_uses_shared_provider_lifecycle() -> None:
    client = _Client(_response(limit=3))
    provider = DataCiteSearchProvider(client)

    await provider.close()
    await provider.close()

    assert client.closed == 1
    with pytest.raises(ProviderError) as error:
        await provider.search(
            _request(), RequestContext(request_id="closed"), ExecutionContext.with_timeout(1)
        )
    assert error.value.code is ProviderErrorCode.INVALID_CONFIG


@pytest.mark.asyncio
async def test_datacite_accepts_legacy_http_landing_url_as_metadata() -> None:
    client = _Client(_response(_result(source_url="http://example.test/record"), limit=3))

    page = await DataCiteSearchProvider(client).search(
        _request(), RequestContext(request_id="http-landing"), ExecutionContext.with_timeout(1)
    )

    assert str(page.items[0].url) == "http://example.test/record"


def test_datacite_manifest_and_bridge_are_anonymous_search_only() -> None:
    assert DATACITE_PROVIDER_MANIFEST.capabilities == ("search",)
    assert DATACITE_PROVIDER_MANIFEST.secrets.all_references == ()
    assert DATACITE_PROVIDER_MANIFEST.network.egress_hosts == ("api.datacite.org",)
    assert DATACITE_PROVIDER_MANIFEST.network.proxy_supported is True
    assert DATACITE_PROVIDER_SPEC.transport.operations[0].endpoint == "/dois"
