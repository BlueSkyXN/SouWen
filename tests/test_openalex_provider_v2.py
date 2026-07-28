"""Deterministic conformance for the OpenAlex Provider v2 adapter."""

from __future__ import annotations

import asyncio

import pytest

from souwen.common_runtime.transport.errors import RateLimitError, SourceUnavailableError
from souwen.common_runtime.provider_support.exceptions import ConfigError
from souwen.providers.runtime_clients.models import Author, PaperResult, SearchResponse
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchFilters,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.openalex import (
    OPENALEX_PROVIDER_MANIFEST,
    OpenAlexSearchProvider,
)


class FakeOpenAlexClient:
    def __init__(self, response: SearchResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.close_count = 0

    async def search(self, query, filters=None, sort=None, page=1, per_page=10):
        self.calls.append(
            {
                "query": query,
                "filters": filters,
                "sort": sort,
                "page": page,
                "per_page": per_page,
            }
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def close(self) -> None:
        self.close_count += 1


def _paper(**overrides: object) -> PaperResult:
    values: dict[str, object] = {
        "source": "openalex",
        "title": "Attention Is All You Need",
        "authors": [Author(name="Ashish Vaswani"), Author(name="Noam Shazeer")],
        "abstract": "A dominant approach to sequence modelling.",
        "doi": "10.1038/s41586-021-03819-2",
        "year": 2017,
        "citation_count": 90000,
        "source_url": "https://openalex.org/W2741809807",
        "raw": {"type": "article", "is_oa": True},
    }
    values.update(overrides)
    return PaperResult(**values)


def _response(*papers: PaperResult, per_page: int = 10) -> SearchResponse:
    return SearchResponse(
        query="attention",
        source="openalex",
        total_results=len(papers),
        page=1,
        per_page=per_page,
        results=list(papers),
    )


def _request(**overrides: object) -> SearchRequest:
    values: dict[str, object] = {
        "query": "attention",
        "domains": ("paper",),
    }
    values.update(overrides)
    return SearchRequest(**values)


def _context() -> RequestContext:
    return RequestContext(request_id="openalex-provider-v2")


def _execution() -> ExecutionContext:
    return ExecutionContext.with_timeout(5)


@pytest.mark.asyncio
async def test_manifest_declares_reviewed_openalex_contract() -> None:
    assert OPENALEX_PROVIDER_MANIFEST.id == "openalex"
    assert OPENALEX_PROVIDER_MANIFEST.capabilities == ("search",)
    assert OPENALEX_PROVIDER_MANIFEST.adapters[0].id == "openalex-search"
    assert OPENALEX_PROVIDER_MANIFEST.adapters[0].availability == "configured"
    assert OPENALEX_PROVIDER_MANIFEST.version == "2.0.0rc3"
    assert OPENALEX_PROVIDER_MANIFEST.secrets.references == ()


@pytest.mark.asyncio
async def test_search_maps_legacy_response_to_canonical_page_and_filters() -> None:
    client = FakeOpenAlexClient(_response(_paper(), per_page=7))
    provider = OpenAlexSearchProvider(client)
    request = _request(
        filters=SearchFilters(
            year_from=2016,
            year_to=2018,
            language="en",
            open_access=True,
            resource_type="article",
        ),
        page=SearchPageRequest(limit=7),
    )

    page = await provider.search(request, _context(), _execution())

    assert client.calls == [
        {
            "query": "attention",
            "filters": {
                "from_publication_date": "2016-01-01",
                "to_publication_date": "2018-12-31",
                "language": "en",
                "is_oa": "true",
                "type": "article",
            },
            "sort": None,
            "page": 1,
            "per_page": 7,
        }
    ]
    assert page.page.limit == 7
    assert page.page.next_cursor is None
    assert page.page.total == 1
    assert page.meta.succeeded == ("openalex",)
    item = page.items[0]
    assert item.id == "doi:10.1038/s41586-021-03819-2"
    assert str(item.url) == "https://doi.org/10.1038/s41586-021-03819-2"
    assert item.rank == 1
    assert item.provenance[0].provider == "openalex"
    assert item.attributes is not None
    assert item.attributes.identifiers[0].scheme == "doi"
    assert item.attributes.identifiers[1].scheme == "openalex"
    assert item.attributes.authors == ("Ashish Vaswani", "Noam Shazeer")
    assert item.attributes.year == 2017
    assert item.attributes.open_access is True
    assert item.attributes.citation_count == 90000


@pytest.mark.asyncio
async def test_openalex_identifier_is_used_when_doi_is_absent() -> None:
    client = FakeOpenAlexClient(_response(_paper(doi=None)))
    provider = OpenAlexSearchProvider(client)

    page = await provider.search(_request(), _context(), _execution())

    assert page.items[0].id == "openalex:https://openalex.org/W2741809807"
    assert str(page.items[0].url) == "https://openalex.org/W2741809807"


@pytest.mark.asyncio
async def test_cursor_and_non_paper_requests_fail_before_legacy_client_call() -> None:
    client = FakeOpenAlexClient(_response(_paper()))
    provider = OpenAlexSearchProvider(client)

    with pytest.raises(ProviderError) as cursor_error:
        await provider.search(
            _request(page=SearchPageRequest(limit=10, cursor="opaque")), _context(), _execution()
        )
    with pytest.raises(ProviderError) as domain_error:
        await provider.search(_request(domains=("web",)), _context(), _execution())
    with pytest.raises(ProviderError) as mixed_domain_error:
        await provider.search(_request(domains=("paper", "web")), _context(), _execution())

    assert cursor_error.value.code is ProviderErrorCode.INVALID_REQUEST
    assert domain_error.value.code is ProviderErrorCode.INVALID_REQUEST
    assert mixed_domain_error.value.code is ProviderErrorCode.INVALID_REQUEST
    assert client.calls == []


@pytest.mark.asyncio
async def test_typed_error_mapping_does_not_expose_legacy_error_text() -> None:
    client = FakeOpenAlexClient(RateLimitError("secret=not-exposed", retry_after=3))
    provider = OpenAlexSearchProvider(client)

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution())

    assert exc_info.value.code is ProviderErrorCode.RATE_LIMITED
    assert exc_info.value.retry_after_seconds == 3
    assert "not-exposed" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (TimeoutError("secret=not-exposed"), ProviderErrorCode.DEADLINE_EXCEEDED),
        (ConfigError("openalex_api_key", "OpenAlex"), ProviderErrorCode.INVALID_CONFIG),
        (SourceUnavailableError("secret=not-exposed"), ProviderErrorCode.PROVIDER_UNAVAILABLE),
    ],
)
async def test_timeout_config_and_unavailable_errors_remain_typed_and_safe(
    failure, expected
) -> None:
    provider = OpenAlexSearchProvider(FakeOpenAlexClient(failure))

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution())

    assert exc_info.value.code is expected
    assert "not-exposed" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_legacy_page_mismatch_fails_closed() -> None:
    mismatched = _response(_paper())
    mismatched.page = 2
    provider = OpenAlexSearchProvider(FakeOpenAlexClient(mismatched))

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution())

    assert exc_info.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


@pytest.mark.asyncio
async def test_invalid_legacy_item_is_classified_without_provider_call_leakage() -> None:
    client = FakeOpenAlexClient(_response(_paper(doi=None, source_url="")))
    provider = OpenAlexSearchProvider(client)

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution())

    assert exc_info.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "paper",
    [
        _paper(doi="not-a-doi"),
        _paper(doi=None, source_url="https://example.com/W2741809807"),
    ],
)
async def test_untrusted_identifiers_fail_closed(paper: PaperResult) -> None:
    provider = OpenAlexSearchProvider(FakeOpenAlexClient(_response(paper)))

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution())

    assert exc_info.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


@pytest.mark.asyncio
async def test_in_flight_cancellation_stops_the_injected_client_call() -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingClient:
        async def search(self, *args, **kwargs):
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    event = asyncio.Event()
    task = asyncio.create_task(
        OpenAlexSearchProvider(BlockingClient()).search(
            _request(),
            _context(),
            ExecutionContext.with_timeout(5, cancel_event=event),
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    event.set()

    with pytest.raises(ProviderError) as exc_info:
        await asyncio.wait_for(task, timeout=1)

    assert exc_info.value.code is ProviderErrorCode.CANCELLED
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_probe_is_local_and_close_is_idempotent() -> None:
    client = FakeOpenAlexClient(_response(_paper()))
    provider = OpenAlexSearchProvider(client)

    probe = await provider.probe(_execution())
    await provider.close()
    await provider.close()
    unavailable = await provider.probe(_execution())

    assert probe.status == "available"
    assert unavailable.status == "unavailable"
    assert client.calls == []
    assert client.close_count == 1


@pytest.mark.asyncio
async def test_cancelled_execution_fails_without_calling_legacy_client() -> None:
    client = FakeOpenAlexClient(_response(_paper()))
    provider = OpenAlexSearchProvider(client)
    event = asyncio.Event()
    event.set()

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(
            _request(), _context(), ExecutionContext.with_timeout(5, cancel_event=event)
        )

    assert exc_info.value.code is ProviderErrorCode.CANCELLED
    assert client.calls == []
