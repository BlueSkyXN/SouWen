"""Deterministic conformance and runtime integration for ERIC Provider v2."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from souwen.common_runtime.transport.errors import RateLimitError, SourceUnavailableError
from souwen.config import SouWenConfig
from souwen.common_runtime.provider_support.exceptions import ConfigError, ParseError
from souwen.delivery.api import create_target_delivery_app
from souwen.providers.runtime_clients.models import Author, PaperResult, SearchResponse
from souwen.platform.provider_manager import ProviderManager, ProviderManagerError
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    ProviderRef,
    RequestContext,
    SearchFilters,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.eric import (
    ERIC_PROVIDER_MANIFEST,
    EricSearchProvider,
)
from souwen.providers.information_sources.openalex import (
    OPENALEX_PROVIDER_MANIFEST,
    OpenAlexSearchProvider,
)
from souwen.server.v2_runtime import build_target_runtime


class FakeEricClient:
    def __init__(self, response: SearchResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.close_count = 0

    async def search(self, query: str, rows: int = 10, start: int = 0):
        self.calls.append({"query": query, "rows": rows, "start": start})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def close(self) -> None:
        self.close_count += 1


class FakeOpenAlexClient:
    def __init__(self) -> None:
        self.close_count = 0

    async def search(self, _query, filters=None, sort=None, page=1, per_page=10):
        del filters, sort
        response = _openalex_response()
        response.page = page
        response.per_page = per_page
        return response

    async def close(self) -> None:
        self.close_count += 1


def _paper(**overrides: object) -> PaperResult:
    values: dict[str, object] = {
        "source": "eric",
        "title": "Teaching Machine Learning in Secondary Schools",
        "authors": [Author(name="Ada Teacher"), Author(name="Grace Researcher")],
        "abstract": "A bounded education-research fixture.",
        "year": 2024,
        "source_url": "https://eric.ed.gov/?id=EJ1234567",
        "raw": {
            "eric_id": "EJ1234567",
            "publication_types": ["Journal Articles"],
            "language": ["English"],
            "fulltext_authorized": True,
        },
    }
    values.update(overrides)
    return PaperResult(**values)


def _response(*papers: PaperResult, per_page: int = 10) -> SearchResponse:
    return SearchResponse(
        query="machine learning",
        source="eric",
        total_results=len(papers),
        page=1,
        per_page=per_page,
        results=list(papers),
    )


def _openalex_response() -> SearchResponse:
    return SearchResponse(
        query="machine learning",
        source="openalex",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            PaperResult(
                source="openalex",
                title="OpenAlex fallback",
                authors=[Author(name="Fallback Author")],
                doi="10.1000/fallback",
                year=2024,
                source_url="https://openalex.org/W1234567890",
                raw={"type": "article", "is_oa": True},
            )
        ],
    )


def _request(**overrides: object) -> SearchRequest:
    values: dict[str, object] = {
        "query": "machine learning",
        "domains": ("paper",),
    }
    values.update(overrides)
    return SearchRequest(**values)


def _context() -> RequestContext:
    return RequestContext(request_id="eric-provider-v2")


def _execution() -> ExecutionContext:
    return ExecutionContext.with_timeout(5)


def test_manifest_declares_reviewed_eric_contract() -> None:
    assert ERIC_PROVIDER_MANIFEST.id == "eric"
    assert ERIC_PROVIDER_MANIFEST.version == "2.0.0rc2"
    assert ERIC_PROVIDER_MANIFEST.contract_version == "provider-v2"
    assert ERIC_PROVIDER_MANIFEST.capabilities == ("search",)
    assert ERIC_PROVIDER_MANIFEST.adapters[0].id == "eric-search"
    assert ERIC_PROVIDER_MANIFEST.adapters[0].export == "EricSearchProvider"
    assert ERIC_PROVIDER_MANIFEST.configuration.non_secret_keys == (
        "enabled",
        "max_retries",
        "timeout_seconds",
    )
    assert ERIC_PROVIDER_MANIFEST.secrets.references == ()
    assert ERIC_PROVIDER_MANIFEST.network.egress_hosts == ("api.ies.ed.gov",)
    assert ERIC_PROVIDER_MANIFEST.network.proxy_supported is False
    assert ERIC_PROVIDER_MANIFEST.network.browser_required is False


@pytest.mark.asyncio
async def test_search_maps_official_response_to_canonical_page() -> None:
    client = FakeEricClient(_response(_paper(), per_page=7))
    provider = EricSearchProvider(client)

    page = await provider.search(
        _request(page=SearchPageRequest(limit=7)),
        _context(),
        _execution(),
    )

    assert client.calls == [{"query": "machine learning", "rows": 7, "start": 0}]
    assert page.page.limit == 7
    assert page.page.next_cursor is None
    assert page.page.total == 1
    assert page.meta.requested == ("eric",)
    assert page.meta.succeeded == ("eric",)
    assert page.meta.failed == ()
    item = page.items[0]
    assert item.id == "eric:EJ1234567"
    assert str(item.url) == "https://eric.ed.gov/?id=EJ1234567"
    assert item.rank == 1
    assert item.provenance[0].provider == "eric"
    assert item.attributes is not None
    assert item.attributes.identifiers[0].model_dump() == {
        "scheme": "eric",
        "value": "EJ1234567",
    }
    assert item.attributes.authors == ("Ada Teacher", "Grace Researcher")
    assert item.attributes.year == 2024
    assert item.attributes.resource_type == "Journal Articles"
    assert item.attributes.language == "English"
    assert item.attributes.open_access is True


@pytest.mark.asyncio
async def test_record_url_host_casing_is_normalized_to_one_canonical_url() -> None:
    page = await EricSearchProvider(
        FakeEricClient(_response(_paper(source_url="https://ERIC.ED.GOV/?id=EJ1234567")))
    ).search(_request(), _context(), _execution())

    assert str(page.items[0].url) == "https://eric.ed.gov/?id=EJ1234567"


@pytest.mark.asyncio
async def test_empty_response_is_canonical_success() -> None:
    page = await EricSearchProvider(FakeEricClient(_response())).search(
        _request(), _context(), _execution()
    )

    assert page.items == ()
    assert page.page.total == 0
    assert page.meta.succeeded == ("eric",)


@pytest.mark.asyncio
async def test_unsupported_domain_cursor_and_filters_fail_before_client_call() -> None:
    client = FakeEricClient(_response(_paper()))
    provider = EricSearchProvider(client)
    requests = (
        _request(domains=("web",)),
        _request(domains=("paper", "web")),
        _request(page=SearchPageRequest(limit=10, cursor="opaque")),
        _request(filters=SearchFilters(year_from=2020)),
    )

    for request in requests:
        with pytest.raises(ProviderError) as exc_info:
            await provider.search(request, _context(), _execution())
        assert exc_info.value.code is ProviderErrorCode.INVALID_REQUEST

    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (RateLimitError("token=not-exposed", retry_after=4), ProviderErrorCode.RATE_LIMITED),
        (TimeoutError("token=not-exposed"), ProviderErrorCode.DEADLINE_EXCEEDED),
        (ConfigError("private", "ERIC"), ProviderErrorCode.INVALID_CONFIG),
        (SourceUnavailableError("token=not-exposed"), ProviderErrorCode.PROVIDER_UNAVAILABLE),
        (ParseError("token=not-exposed"), ProviderErrorCode.INVALID_UPSTREAM_RESPONSE),
        (RuntimeError("token=not-exposed"), ProviderErrorCode.PROVIDER_UNAVAILABLE),
    ],
)
async def test_error_categories_are_safe_and_distinct(failure: Exception, expected) -> None:
    provider = EricSearchProvider(FakeEricClient(failure))

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution())

    assert exc_info.value.code is expected
    assert "not-exposed" not in str(exc_info.value)
    if expected is ProviderErrorCode.RATE_LIMITED:
        assert exc_info.value.retry_after_seconds == 4


@pytest.mark.asyncio
async def test_policy_blocked_provider_error_is_preserved() -> None:
    provider = EricSearchProvider(
        FakeEricClient(ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id="eric"))
    )

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution())

    assert exc_info.value.code is ProviderErrorCode.POLICY_BLOCKED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        SearchResponse(
            query="machine learning",
            source="wrong",
            total_results=1,
            page=1,
            per_page=10,
            results=[_paper()],
        ),
        _response(_paper(raw={"eric_id": "invalid"})),
        _response(_paper(source_url="https://example.com/?id=EJ1234567")),
        _response(_paper(source_url="https://eric.ed.gov/?id=EJ7654321")),
        _response(_paper(source_url="https://user:password@eric.ed.gov/?id=EJ1234567")),
        _response(_paper(source_url="https://eric.ed.gov:443/?id=EJ1234567")),
        _response(_paper(source_url="https://eric.ed.gov/?id=EJ1234567#fragment")),
        _response(_paper(source_url="https://eric.ed.gov/?id=EJ1234567&extra=value")),
        _response(_paper(source_url="https://eric.ed.gov/?id=EJ1234567&unused=")),
        _response(_paper(source_url="https://eric.ed.gov/?id=EJ1234567&id=EJ1234567")),
        _response(_paper(source_url="https://eric.ed.gov/?%69d=EJ1234567")),
    ],
)
async def test_invalid_upstream_identity_and_url_fail_closed(response: SearchResponse) -> None:
    provider = EricSearchProvider(FakeEricClient(response))

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution())

    assert exc_info.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("page", 2),
        ("per_page", 9),
        ("total_results", -1),
    ],
)
async def test_invalid_upstream_page_metadata_fails_closed(field: str, value: int) -> None:
    response = _response(_paper())
    setattr(response, field, value)

    with pytest.raises(ProviderError) as exc_info:
        await EricSearchProvider(FakeEricClient(response)).search(
            _request(), _context(), _execution()
        )

    assert exc_info.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "limit"),
    [
        (_response(_paper(), _paper(), per_page=1), 1),
        (_response(_paper(), _paper()), 10),
    ],
)
async def test_inconsistent_result_count_or_total_fails_closed(
    response: SearchResponse,
    limit: int,
) -> None:
    if limit == 10:
        response.total_results = 1

    with pytest.raises(ProviderError) as exc_info:
        await EricSearchProvider(FakeEricClient(response)).search(
            _request(page=SearchPageRequest(limit=limit)),
            _context(),
            _execution(),
        )

    assert exc_info.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


@pytest.mark.asyncio
async def test_in_flight_cancellation_cancels_and_awaits_client_task() -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingClient:
        async def search(self, *_args, **_kwargs):
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    cancel_event = asyncio.Event()
    task = asyncio.create_task(
        EricSearchProvider(BlockingClient()).search(
            _request(),
            _context(),
            ExecutionContext.with_timeout(5, cancel_event=cancel_event),
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    cancel_event.set()

    with pytest.raises(ProviderError) as exc_info:
        await asyncio.wait_for(task, timeout=1)

    assert exc_info.value.code is ProviderErrorCode.CANCELLED
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_in_flight_deadline_cancels_and_awaits_client_task() -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingClient:
        async def search(self, *_args, **_kwargs):
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    task = asyncio.create_task(
        EricSearchProvider(BlockingClient()).search(
            _request(),
            _context(),
            ExecutionContext.with_timeout(0.05),
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)

    with pytest.raises(ProviderError) as exc_info:
        await asyncio.wait_for(task, timeout=1)

    assert exc_info.value.code is ProviderErrorCode.DEADLINE_EXCEEDED
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_outer_task_cancellation_propagates_and_cleans_client_task() -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingClient:
        async def search(self, *_args, **_kwargs):
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    provider = EricSearchProvider(BlockingClient())
    task = asyncio.create_task(provider.search(_request(), _context(), _execution()))
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancelled.is_set()
    await provider.close()
    assert (await provider.probe(_execution())).status == "unavailable"


@pytest.mark.asyncio
async def test_pre_cancelled_execution_does_not_call_client() -> None:
    client = FakeEricClient(_response(_paper()))
    event = asyncio.Event()
    event.set()

    with pytest.raises(ProviderError) as exc_info:
        await EricSearchProvider(client).search(
            _request(),
            _context(),
            ExecutionContext.with_timeout(5, cancel_event=event),
        )

    assert exc_info.value.code is ProviderErrorCode.CANCELLED
    assert client.calls == []


@pytest.mark.asyncio
async def test_probe_is_local_and_close_is_idempotent() -> None:
    client = FakeEricClient(_response(_paper()))
    provider = EricSearchProvider(client)

    available = await provider.probe(_execution())
    await provider.close()
    await provider.close()
    unavailable = await provider.probe(_execution())

    assert available.provider == unavailable.provider == "eric"
    assert available.capability == unavailable.capability == "search"
    assert available.status == "available"
    assert unavailable.status == "unavailable"
    assert client.calls == []
    assert client.close_count == 1

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution())
    assert exc_info.value.code is ProviderErrorCode.INVALID_CONFIG
    assert client.calls == []


@pytest.mark.asyncio
async def test_disabled_provider_is_locally_unavailable_and_never_calls_client() -> None:
    client = FakeEricClient(_response(_paper()))
    provider = EricSearchProvider(client, enabled=False)

    probe = await provider.probe(_execution())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution())

    assert probe.status == "unavailable"
    assert exc_info.value.code is ProviderErrorCode.INVALID_CONFIG
    assert client.calls == []


@pytest.mark.asyncio
async def test_cancelled_close_can_be_retried() -> None:
    class CancellingCloser(FakeEricClient):
        async def close(self) -> None:
            self.close_count += 1
            if self.close_count == 1:
                raise asyncio.CancelledError

    client = CancellingCloser(_response(_paper()))
    provider = EricSearchProvider(client)

    with pytest.raises(asyncio.CancelledError):
        await provider.close()
    assert (await provider.probe(_execution())).status == "available"

    await provider.close()

    assert client.close_count == 2
    assert (await provider.probe(_execution())).status == "unavailable"


@pytest.mark.asyncio
async def test_manager_config_failure_is_local_and_diagnostics_are_safe() -> None:
    constructed = 0

    def resolve(manifest):
        if manifest.id == "eric":
            raise RuntimeError("token=manager-config-canary")
        return {"enabled": True}

    manager = ProviderManager(config_resolver=resolve)

    def eric_factory(_configuration, _secrets):
        nonlocal constructed
        constructed += 1
        return EricSearchProvider(FakeEricClient(_response(_paper())))

    openalex_client = FakeOpenAlexClient()
    manager.register_factory(
        package_id="eric",
        export="EricSearchProvider",
        factory=eric_factory,
        provider_type=EricSearchProvider,
    )
    manager.register_factory(
        package_id="openalex",
        export="OpenAlexSearchProvider",
        factory=lambda _configuration, _secrets: OpenAlexSearchProvider(openalex_client),
        provider_type=OpenAlexSearchProvider,
    )
    manager.discover((ERIC_PROVIDER_MANIFEST, OPENALEX_PROVIDER_MANIFEST))

    assert constructed == 0
    assert "eric-search" not in manager.eligible_adapter_ids
    assert "openalex-search" in manager.eligible_adapter_ids
    diagnostic = next(item for item in manager.diagnostics if item.package_id == "eric")
    assert diagnostic.reason_code == "config_invalid"
    assert "canary" not in repr(diagnostic)

    page = await manager.execute("openalex-search", _request(), _context(), _execution())
    assert page.items[0].id == "doi:10.1000/fallback"
    await manager.close_all()


@pytest.mark.asyncio
async def test_manager_close_failure_is_safe_and_other_provider_still_closes() -> None:
    class FailingCloseClient(FakeEricClient):
        async def close(self) -> None:
            self.close_count += 1
            raise RuntimeError("token=close-canary")

    eric_client = FailingCloseClient(_response(_paper()))
    openalex_client = FakeOpenAlexClient()
    manager = ProviderManager(config_resolver=lambda _manifest: {"enabled": True})
    manager.register_factory(
        package_id="eric",
        export="EricSearchProvider",
        factory=lambda _configuration, _secrets: EricSearchProvider(eric_client),
        provider_type=EricSearchProvider,
    )
    manager.register_factory(
        package_id="openalex",
        export="OpenAlexSearchProvider",
        factory=lambda _configuration, _secrets: OpenAlexSearchProvider(openalex_client),
        provider_type=OpenAlexSearchProvider,
    )
    manager.discover((ERIC_PROVIDER_MANIFEST, OPENALEX_PROVIDER_MANIFEST))
    await manager.execute("eric-search", _request(), _context(), _execution())
    await manager.execute("openalex-search", _request(), _context(), _execution())

    with pytest.raises(ProviderManagerError) as exc_info:
        await manager.close_all()

    assert exc_info.value.code == "close_failed"
    assert "canary" not in str(exc_info.value)
    assert eric_client.close_count == 1
    assert openalex_client.close_count == 1
    diagnostic = next(
        item
        for item in manager.diagnostics
        if item.package_id == "eric" and item.reason_code == "close_failed"
    )
    assert "canary" not in repr(diagnostic)


def test_delivery_routes_use_lazy_explicit_eric_transport_and_safe_catalog(monkeypatch) -> None:
    transport_options: list[dict[str, object]] = []
    transport_calls: list[dict[str, object]] = []
    transports = []

    class RuntimeTransport:
        def __init__(self, **options) -> None:
            transport_options.append(options)
            transports.append(self)
            self.close_count = 0

        async def get(self, url, params=None, **_kwargs):
            transport_calls.append({"url": url, "params": params})
            return httpx.Response(
                200,
                json={
                    "response": {
                        "numFound": 1,
                        "docs": [
                            {
                                "id": "EJ1234567",
                                "title": "Teaching Machine Learning in Secondary Schools",
                                "author": ["Ada Teacher"],
                                "description": "A bounded education-research fixture.",
                                "publicationdateyear": "2024",
                                "publicationtype": ["Journal Articles"],
                                "language": ["English"],
                                "e_fulltextauth": 1,
                            }
                        ],
                    }
                },
            )

        async def close(self) -> None:
            self.close_count += 1

    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    monkeypatch.setattr("souwen.server.v2_runtime.HttpTransport", RuntimeTransport)
    runtime = build_target_runtime(
        SouWenConfig(
            timeout=30,
            max_retries=2,
            sources={"eric": {"timeout": 7}},
        )
    )

    assert transport_options == []
    assert "eric-search" in runtime.manager.eligible_adapter_ids
    app = create_target_delivery_app(
        runtime.services,
        runtime.metadata,
        require_user=lambda: None,
        rate_limit=lambda: None,
        closer=runtime.close,
    )
    headers = {"X-Request-ID": "eric-delivery-v2", "X-SouWen-API-Major": "2"}
    with TestClient(app, raise_server_exceptions=False) as client:
        providers = client.get("/api/v1/providers", headers=headers)
        search = client.post(
            "/api/v1/search",
            headers=headers,
            json={
                "query": "machine learning",
                "domains": ["paper"],
                "providers": [{"id": "eric", "kind": "search"}],
                "page": {"limit": 6},
            },
        )

        assert providers.status_code == 200
        by_id = {item["provider"]: item for item in providers.json()["items"]}
        assert by_id["eric"] == {
            "provider": "eric",
            "capabilities": ["search"],
            "availability": "available",
            "provenance": [
                {
                    "provider": "eric",
                    "attempt": None,
                    "outcome": "success",
                    "retrieved_at": None,
                }
            ],
            "reason": "available",
            "missing_fields": [],
        }
        assert search.status_code == 200
        payload = search.json()
        assert payload["items"][0]["id"] == "eric:EJ1234567"
        assert payload["meta"]["requested"] == ["eric"]
        assert payload["meta"]["succeeded"] == ["eric"]
        assert payload["context"]["request_id"] == "eric-delivery-v2"

    assert transport_options == [
        {
            "base_url": "https://api.ies.ed.gov",
            "headers": {"User-Agent": "SouWen/2.0.0rc2"},
            "timeout": 7,
            "max_retries": 2,
            "proxy": None,
            "follow_redirects": False,
        }
    ]
    assert transport_calls == [
        {
            "url": "/eric/",
            "params": {
                "search": "machine learning",
                "format": "json",
                "start": "0",
                "rows": "6",
            },
        }
    ]
    assert transports[0].close_count == 1


@pytest.mark.asyncio
async def test_disabled_eric_keeps_openalex_default_and_never_constructs_eric(monkeypatch) -> None:
    eric_transport_constructions = 0
    openalex_calls = 0

    class _Http:
        async def close(self) -> None:
            return None

    class RuntimeOpenAlexClient:
        def __init__(self, *_args, **_kwargs) -> None:
            self._client = _Http()

        async def search(self, *_args, **_kwargs):
            nonlocal openalex_calls
            openalex_calls += 1
            return _openalex_response()

    def forbidden_eric_transport(**_options):
        nonlocal eric_transport_constructions
        eric_transport_constructions += 1
        raise AssertionError("disabled ERIC must not construct transport")

    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    monkeypatch.setattr("souwen.server.v2_runtime.OpenAlexClient", RuntimeOpenAlexClient)
    monkeypatch.setattr("souwen.server.v2_runtime.HttpTransport", forbidden_eric_transport)
    runtime = build_target_runtime(SouWenConfig(sources={"eric": {"enabled": False}}))

    by_id = {item.provider: item for item in runtime.services.provider_items}
    assert by_id["eric"].availability == "unavailable"
    assert by_id["eric"].reason == "disabled"
    assert "eric-search" not in runtime.manager.eligible_adapter_ids

    default_page = await runtime.services.search.search(_request(), _context(), _execution())
    assert default_page.meta.requested == ("openalex",)
    assert default_page.items[0].id == "doi:10.1000/fallback"

    with pytest.raises(ProviderError) as exc_info:
        await runtime.services.search.search(
            _request(providers=(ProviderRef(id="eric", kind="search"),)),
            _context(),
            _execution(),
        )
    assert exc_info.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert openalex_calls == 1
    assert eric_transport_constructions == 0
    await runtime.close()


@pytest.mark.asyncio
async def test_invalid_eric_transport_config_is_ineligible_before_factory_construction(
    monkeypatch,
) -> None:
    transport_constructions = 0

    def forbidden_transport(**_options):
        nonlocal transport_constructions
        transport_constructions += 1
        raise AssertionError("invalid ERIC config must fail during preflight")

    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    monkeypatch.setattr("souwen.server.v2_runtime.HttpTransport", forbidden_transport)
    runtime = build_target_runtime(SouWenConfig(sources={"eric": {"timeout": 121}}))

    by_id = {item.provider: item for item in runtime.services.provider_items}
    assert "eric-search" not in runtime.manager.eligible_adapter_ids
    assert by_id["eric"].availability == "unavailable"
    assert by_id["eric"].reason == "not_eligible"
    diagnostic = next(item for item in runtime.manager.diagnostics if item.package_id == "eric")
    assert diagnostic.reason_code == "config_invalid"

    with pytest.raises(ProviderError) as exc_info:
        await runtime.services.search.search(
            _request(providers=(ProviderRef(id="eric", kind="search"),)),
            _context(),
            _execution(),
        )

    assert exc_info.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert transport_constructions == 0
    await runtime.close()
