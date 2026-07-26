"""Deterministic Provider v2 checks for Figshare research-output Search."""

from __future__ import annotations

import pytest

from souwen.models import (
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
from souwen.providers.information_sources.figshare import (
    FIGSHARE_PROVIDER_MANIFEST,
    FIGSHARE_PROVIDER_SPEC,
    FigshareSearchProvider,
)


class _Client:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, int, int]] = []
        self.closed = 0

    async def search(self, query: str, page_size: int = 10, page: int = 1) -> SearchResponse:
        self.calls.append((query, page_size, page))
        return self.response

    async def close(self) -> None:
        self.closed += 1


def _result(**overrides: object) -> ResearchOutputResult:
    values: dict[str, object] = {
        "source": "figshare",
        "source_record_id": "33046703",
        "title": "Climate software",
        "creators": [ResearchContributor(name="Ada Author")],
        "publication_year": 2025,
        "resource_type_general": "Software",
        "resource_type": "software",
        "language": "en",
        "identifiers": [
            ResearchOutputIdentifier(scheme="doi", value="10.6084/m9.figshare.33046703.v1"),
            ResearchOutputIdentifier(scheme="figshare_article_id", value="33046703"),
        ],
        "access": ResourceAccess(status="metadata_only"),
        "resources": [
            ResourceLink(
                url="https://ndownloader.figshare.com/files/1",
                relation="declared_file_url",
                source="figshare",
                is_link_only=True,
                access=ResourceAccess(status="metadata_only"),
            )
        ],
        "source_url": "https://figshare.com/articles/software/climate/33046703",
    }
    values.update(overrides)
    return ResearchOutputResult(**values)


def _response(
    *items: ResearchOutputResult, total: int | None = None, limit: int = 4
) -> SearchResponse:
    return SearchResponse(
        query="climate",
        source="figshare",
        total_results=total,
        page=1,
        per_page=limit,
        results=list(items),
    )


def _request() -> SearchRequest:
    return SearchRequest(
        query="climate",
        domains=("research_output",),
        page=SearchPageRequest(limit=4),
    )


@pytest.mark.asyncio
async def test_figshare_projects_safe_metadata_without_detail_or_file_fanout() -> None:
    client = _Client(_response(_result(), limit=4))
    page = await FigshareSearchProvider(client).search(
        _request(), RequestContext(request_id="figshare"), ExecutionContext.with_timeout(1)
    )

    assert client.calls == [("climate", 4, 1)]
    item = page.items[0]
    assert item.id == "figshare:33046703"
    assert str(item.url) == "https://figshare.com/articles/software/climate/33046703"
    assert item.attributes is not None
    assert item.attributes.year == 2025
    assert item.attributes.authors == ("Ada Author",)
    assert item.attributes.resource_type == "Software"
    assert item.attributes.language == "en"
    assert item.attributes.open_access is None
    assert {(value.scheme, value.value) for value in item.attributes.identifiers} == {
        ("figshare", "33046703"),
        ("doi", "10.6084/m9.figshare.33046703.v1"),
        ("figshare_article_id", "33046703"),
    }
    assert item.snippet is None
    assert "resources" not in item.model_dump()
    assert "raw" not in item.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        SearchResponse(query="climate", source="datacite", page=1, per_page=4, results=[]),
        _response(_result(source="datacite"), limit=4),
        _response(_result(title=""), limit=4),
        _response(_result(source_record_id=""), limit=4),
        _response(_result(), total=0, limit=4),
        _response(_result(), limit=3),
    ],
)
async def test_figshare_rejects_invalid_legacy_projection(response: SearchResponse) -> None:
    with pytest.raises(ProviderError) as error:
        await FigshareSearchProvider(_Client(response)).search(
            _request(), RequestContext(request_id="invalid"), ExecutionContext.with_timeout(1)
        )
    assert error.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


@pytest.mark.asyncio
async def test_figshare_uses_shared_provider_lifecycle() -> None:
    client = _Client(_response(limit=4))
    provider = FigshareSearchProvider(client)

    await provider.close()
    await provider.close()

    assert client.closed == 1
    with pytest.raises(ProviderError) as error:
        await provider.search(
            _request(), RequestContext(request_id="closed"), ExecutionContext.with_timeout(1)
        )
    assert error.value.code is ProviderErrorCode.INVALID_CONFIG


def test_figshare_manifest_and_bridge_are_anonymous_search_only() -> None:
    assert FIGSHARE_PROVIDER_MANIFEST.capabilities == ("search",)
    assert FIGSHARE_PROVIDER_MANIFEST.secrets.all_references == ()
    assert FIGSHARE_PROVIDER_MANIFEST.network.egress_hosts == ("api.figshare.com",)
    assert FIGSHARE_PROVIDER_MANIFEST.network.proxy_supported is True
    assert FIGSHARE_PROVIDER_SPEC.transport.operations[0].endpoint == "/articles/search"
