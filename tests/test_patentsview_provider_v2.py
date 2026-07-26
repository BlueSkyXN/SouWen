"""Deterministic conformance and runtime integration for PatentsView Provider v2."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from souwen.common_runtime.transport.errors import AuthError, RateLimitError
from souwen.config import SouWenConfig
from souwen.delivery.api import create_target_delivery_app
from souwen.models import Applicant, PatentResult, SearchResponse
from souwen.modules.search.application import OrderedSearchProviderSelector, SearchProviderSelection
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
from souwen.providers.information_sources.patentsview import (
    PATENTSVIEW_PROVIDER_MANIFEST,
    PatentsViewSearchProvider,
)
from souwen.registry import get
from souwen.server.v2_runtime import build_target_runtime


class FakeClient:
    def __init__(self, response: SearchResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.close_count = 0

    async def search(self, query, fields=None, per_page=10, page=1, sort=None):
        self.calls.append(
            {
                "query": query,
                "fields": fields,
                "per_page": per_page,
                "page": page,
                "sort": sort,
            }
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def close(self) -> None:
        self.close_count += 1


def _patent(**overrides) -> PatentResult:
    values = {
        "source": "patentsview",
        "title": "Bounded neural-network patent",
        "patent_id": "11234567",
        "application_number": "US17/123456",
        "publication_date": date(2023, 1, 31),
        "filing_date": date(2021, 6, 15),
        "applicants": [Applicant(name="Example Corp", country="US")],
        "inventors": ["Ada Inventor", "Grace Engineer"],
        "abstract": "A deterministic patent fixture.",
        "cpc_codes": ["G06N3/08"],
        "ipc_codes": ["G06N3/00"],
        "source_url": "https://search.patentsview.org/patent/11234567",
        "raw": {"patent_type": "utility"},
    }
    values.update(overrides)
    return PatentResult(**values)


def _response(*patents: PatentResult, per_page: int = 10) -> SearchResponse:
    return SearchResponse(
        query="fixture",
        source="patentsview",
        total_results=len(patents),
        page=1,
        per_page=per_page,
        results=list(patents),
    )


def _request(**overrides) -> SearchRequest:
    values = {"query": "neural network", "domains": ("patent",)}
    values.update(overrides)
    return SearchRequest(**values)


def _context() -> RequestContext:
    return RequestContext(request_id="patentsview-provider-v2")


def _execution(timeout: float = 5) -> ExecutionContext:
    return ExecutionContext.with_timeout(timeout)


def test_manifest_matches_legacy_registry_and_required_secret_contract() -> None:
    legacy = get("patentsview")

    assert PATENTSVIEW_PROVIDER_MANIFEST.id == legacy.name == "patentsview"
    assert PATENTSVIEW_PROVIDER_MANIFEST.adapters[0].id == "patentsview-search"
    assert PATENTSVIEW_PROVIDER_MANIFEST.capabilities == ("search",)
    assert PATENTSVIEW_PROVIDER_MANIFEST.secrets.references == ("PATENTSVIEW_API_KEY",)
    assert PATENTSVIEW_PROVIDER_MANIFEST.network.egress_hosts == ("search.patentsview.org",)
    assert PATENTSVIEW_PROVIDER_MANIFEST.network.proxy_supported is False
    assert legacy.domain == "patent"
    assert legacy.resolved_auth_requirement == "required"
    assert legacy.default_for == frozenset()


def test_legacy_flat_secret_is_excluded_from_config_repr() -> None:
    config = SouWenConfig(patentsview_api_key="flat-secret-canary")

    assert config.resolve_api_key("patentsview", "patentsview_api_key") == "flat-secret-canary"
    assert "flat-secret-canary" not in repr(config)


def test_selector_registers_patentsview_for_explicit_selection_only() -> None:
    selection = SearchProviderSelection(
        provider=ProviderRef(id="patentsview", kind="search"),
        adapter_id="patentsview-search",
        yaml_priority=1,
    )
    selector = OrderedSearchProviderSelector({}, explicit_selections=(selection,))

    assert selector.select_explicit((selection.provider,)) == (selection,)
    with pytest.raises(ProviderError) as exc_info:
        selector.select_default(_request())
    assert exc_info.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE


@pytest.mark.asyncio
async def test_search_maps_bounded_patent_projection_and_dict_query() -> None:
    client = FakeClient(_response(_patent(), per_page=7))
    page = await PatentsViewSearchProvider(client).search(
        _request(page=SearchPageRequest(limit=7)), _context(), _execution()
    )

    assert client.calls == [
        {
            "query": {"_contains": {"patent_title": "neural network"}},
            "fields": None,
            "per_page": 7,
            "page": 1,
            "sort": None,
        }
    ]
    item = page.items[0]
    assert item.id == "patentsview:11234567"
    assert str(item.url) == "https://search.patentsview.org/patent/11234567"
    assert item.attributes is not None
    assert item.attributes.year == 2023
    assert item.attributes.identifiers[0].model_dump() == {
        "scheme": "patentsview",
        "value": "11234567",
    }
    assert item.attributes.authors == ()
    assert item.attributes.resource_type == "patent"
    assert "application_number" not in item.model_dump()
    assert page.meta.succeeded == ("patentsview",)


@pytest.mark.asyncio
async def test_invalid_domain_cursor_and_filters_fail_before_client_call() -> None:
    client = FakeClient(_response(_patent()))
    provider = PatentsViewSearchProvider(client)
    requests = (
        _request(domains=("paper",)),
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
    ("failure", "code"),
    [
        (AuthError("secret-canary"), ProviderErrorCode.INVALID_CONFIG),
        (RateLimitError("secret-canary", retry_after=3), ProviderErrorCode.RATE_LIMITED),
        (RuntimeError("secret-canary"), ProviderErrorCode.PROVIDER_UNAVAILABLE),
    ],
)
async def test_error_mapping_is_typed_and_redacted(failure: Exception, code) -> None:
    with pytest.raises(ProviderError) as exc_info:
        await PatentsViewSearchProvider(FakeClient(failure)).search(
            _request(), _context(), _execution()
        )

    assert exc_info.value.code is code
    assert "secret-canary" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_deadline_cancels_child_and_close_is_idempotent() -> None:
    cancelled = asyncio.Event()

    class BlockingClient(FakeClient):
        async def search(self, *_args, **_kwargs):
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    client = BlockingClient(_response())
    provider = PatentsViewSearchProvider(client)
    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request(), _context(), _execution(0.03))
    assert exc_info.value.code is ProviderErrorCode.DEADLINE_EXCEEDED
    assert cancelled.is_set()

    probe = await provider.probe(_execution())
    assert (probe.provider, probe.capability, probe.status) == (
        "patentsview",
        "search",
        "available",
    )
    await provider.close()
    await provider.close()
    assert client.close_count == 1


@pytest.mark.parametrize("api_key", [None, "   "])
def test_missing_secret_is_safe_and_does_not_become_patent_default(monkeypatch, api_key) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    source = {"enabled": True}
    if api_key is not None:
        source["api_key"] = api_key
    runtime = build_target_runtime(SouWenConfig(sources={"patentsview": source}))
    by_id = {item.provider: item for item in runtime.services.provider_items}

    assert "patentsview-search" not in runtime.manager.eligible_adapter_ids
    assert by_id["patentsview"].availability == "unavailable"
    assert by_id["patentsview"].reason == "missing_configuration"
    assert by_id["patentsview"].missing_fields == ("patentsview_api_key",)
    assert "PATENTSVIEW_API_KEY" not in repr(runtime.services.provider_items)

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(runtime.services.search.search(_request(), _context(), _execution()))
    assert exc_info.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    asyncio.run(runtime.close())


def test_delivery_explicit_patentsview_uses_lazy_secret_transport(monkeypatch) -> None:
    options: list[dict[str, object]] = []
    calls = 0

    class RuntimeTransport:
        def __init__(self, **kwargs) -> None:
            options.append(kwargs)

        async def post(self, _url, json=None, **_kwargs):
            nonlocal calls
            calls += 1
            assert json["q"] == {"_contains": {"patent_title": "neural network"}}
            return httpx.Response(
                200,
                json={
                    "patents": [
                        {
                            "patent_id": "11234567",
                            "patent_title": "Bounded neural-network patent",
                            "patent_abstract": "A deterministic patent fixture.",
                            "patent_date": "2023-01-31",
                            "inventors": [],
                            "assignees": [],
                            "cpcs": [],
                            "ipcs": [],
                            "patent_type": "utility",
                        }
                    ],
                    "total_patent_count": 1,
                },
            )

        async def close(self) -> None:
            return None

    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    monkeypatch.setattr("souwen.server.v2_runtime.HttpTransport", RuntimeTransport)
    runtime = build_target_runtime(
        SouWenConfig(sources={"patentsview": {"enabled": True, "api_key": "secret-canary"}})
    )
    assert options == []
    app = create_target_delivery_app(
        runtime.services,
        runtime.metadata,
        require_user=lambda: None,
        rate_limit=lambda: None,
        closer=runtime.close,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/search",
            headers={"X-Request-ID": "patentsview-delivery", "X-SouWen-API-Major": "2"},
            json={
                "query": "neural network",
                "domains": ["patent"],
                "providers": [{"id": "patentsview", "kind": "search"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "patentsview:11234567"
    assert calls == 1
    assert options[0]["base_url"] == "https://search.patentsview.org/api/v1"
    assert options[0]["headers"]["X-Api-Key"] == "secret-canary"
    assert "secret-canary" not in response.text


def test_enabled_configured_patentsview_is_eligible(monkeypatch) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = build_target_runtime(
        SouWenConfig(sources={"patentsview": {"enabled": True, "api_key": "secret-canary"}})
    )

    assert "patentsview-search" in runtime.manager.eligible_adapter_ids
    assert "secret-canary" not in repr(runtime.manager.diagnostics)
    asyncio.run(runtime.close())
