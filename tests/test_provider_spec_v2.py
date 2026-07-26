"""Focused deterministic coverage for typed Provider v2 spec/factory primitives."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from souwen.platform.provider_spec import (
    CredentialBinding,
    LegacyFetchProvider,
    LegacyFetchSpec,
    LegacySearchProviderSpec,
    LegacyTransportDeclaration,
    LegacySearchProvider,
    LegacySearchSpec,
    RestJsonProviderSpec,
    RestJsonSearchProvider,
    resolve_provider_inputs,
    validate_spec_manifest,
)
from souwen.platform.provider_spec.models import (
    AuthDeclaration,
    SearchRequestMapping,
    SearchResponseMapping,
)
from souwen.platform.provider_spi import (
    ContentMetadata,
    ExecutionContext,
    FetchResult,
    FetchTargetRequest,
    PageInfo,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    RequestContext,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)
from souwen.providers.information_sources.eric import ERIC_PROVIDER_MANIFEST, ERIC_REST_SPEC
from souwen.providers.fetch_sources.arxiv_fulltext import (
    ARXIV_FULLTEXT_FETCH_PROFILE,
    ARXIV_FULLTEXT_PROVIDER_MANIFEST,
)
from souwen.providers.information_sources.arxiv import (
    ARXIV_PROVIDER_MANIFEST,
    ARXIV_PROVIDER_SPEC,
)
from souwen.providers.information_sources.biorxiv import (
    BIORXIV_PROVIDER_MANIFEST,
    BIORXIV_PROVIDER_SPEC,
)
from souwen.providers.information_sources.crossref import (
    CROSSREF_PROVIDER_MANIFEST,
    CROSSREF_PROVIDER_SPEC,
)
from souwen.providers.information_sources.dblp import DBLP_PROVIDER_MANIFEST, DBLP_PROVIDER_SPEC
from souwen.providers.information_sources.europepmc import (
    EUROPEPMC_PROVIDER_MANIFEST,
    EUROPEPMC_PROVIDER_SPEC,
)
from souwen.providers.information_sources.google_patents import (
    GOOGLE_PATENTS_BRIDGE_SPEC,
    GOOGLE_PATENTS_PROVIDER_MANIFEST,
)
from souwen.providers.information_sources.hal import HAL_PROVIDER_MANIFEST, HAL_PROVIDER_SPEC
from souwen.providers.information_sources.huggingface import (
    HUGGINGFACE_PROVIDER_MANIFEST,
    HUGGINGFACE_REST_SPEC,
)
from souwen.providers.information_sources.iacr import IACR_BRIDGE_SPEC, IACR_PROVIDER_MANIFEST
from souwen.providers.information_sources.openalex import (
    OPENALEX_PROVIDER_MANIFEST,
    OPENALEX_REST_SPEC,
)
from souwen.providers.information_sources.osti import OSTI_BRIDGE_SPEC, OSTI_PROVIDER_MANIFEST
from souwen.providers.information_sources.patentsview import (
    PATENTSVIEW_PROVIDER_MANIFEST,
    PATENTSVIEW_REST_SPEC,
)
from souwen.providers.information_sources.pmc import PMC_BRIDGE_SPEC, PMC_PROVIDER_MANIFEST
from souwen.providers.information_sources.pubmed import (
    PUBMED_BRIDGE_SPEC,
    PUBMED_PROVIDER_MANIFEST,
)


def _context() -> RequestContext:
    return RequestContext(request_id="provider-spec")


def _page(_response, limit: int, context: RequestContext) -> SearchPage:
    return SearchPage(
        items=(
            SearchItem(
                id="fixture:1",
                title="fixture",
                provenance=(Provenance(provider="fixture", outcome="success"),),
            ),
        ),
        page=PageInfo(limit=limit, total=1),
        meta=SearchMeta(requested=("fixture",), succeeded=("fixture",)),
        context=context,
    )


class _Client:
    def __init__(self, response: object = object()) -> None:
        self.response, self.closed = response, 0

    async def search(self, *_args, **_kwargs):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def close(self) -> None:
        self.closed += 1


def test_static_specs_are_value_free_and_readable() -> None:
    assert ERIC_REST_SPEC.base_url == "https://api.ies.ed.gov"
    assert ERIC_REST_SPEC.adapter_kind == "generic_rest_json"
    assert ERIC_REST_SPEC.operation.method == "GET"
    assert ERIC_REST_SPEC.request_mapping.fixed_fields == {"start": 0}
    assert ERIC_REST_SPEC.response_mapping is not None
    assert OPENALEX_REST_SPEC.host == "api.openalex.org"
    assert OPENALEX_REST_SPEC.adapter_kind == "legacy_bridge"
    assert OPENALEX_REST_SPEC.bridge_reason is not None
    assert PATENTSVIEW_REST_SPEC.auth_reference == "PATENTSVIEW_API_KEY"
    assert PATENTSVIEW_REST_SPEC.auth.placement == "header"
    assert PATENTSVIEW_REST_SPEC.bridge_reason is not None


def test_each_sample_spec_agrees_with_its_governance_manifest() -> None:
    assert validate_spec_manifest(ERIC_REST_SPEC, ERIC_PROVIDER_MANIFEST) is ERIC_REST_SPEC
    assert (
        validate_spec_manifest(OPENALEX_REST_SPEC, OPENALEX_PROVIDER_MANIFEST) is OPENALEX_REST_SPEC
    )


@pytest.mark.parametrize(
    ("spec", "manifest"),
    (
        (ARXIV_PROVIDER_SPEC, ARXIV_PROVIDER_MANIFEST),
        (ARXIV_FULLTEXT_FETCH_PROFILE, ARXIV_FULLTEXT_PROVIDER_MANIFEST),
        (BIORXIV_PROVIDER_SPEC, BIORXIV_PROVIDER_MANIFEST),
        (CROSSREF_PROVIDER_SPEC, CROSSREF_PROVIDER_MANIFEST),
        (DBLP_PROVIDER_SPEC, DBLP_PROVIDER_MANIFEST),
        (EUROPEPMC_PROVIDER_SPEC, EUROPEPMC_PROVIDER_MANIFEST),
        (GOOGLE_PATENTS_BRIDGE_SPEC, GOOGLE_PATENTS_PROVIDER_MANIFEST),
        (HAL_PROVIDER_SPEC, HAL_PROVIDER_MANIFEST),
        (HUGGINGFACE_REST_SPEC, HUGGINGFACE_PROVIDER_MANIFEST),
        (IACR_BRIDGE_SPEC, IACR_PROVIDER_MANIFEST),
        (OSTI_BRIDGE_SPEC, OSTI_PROVIDER_MANIFEST),
        (PMC_BRIDGE_SPEC, PMC_PROVIDER_MANIFEST),
        (PUBMED_BRIDGE_SPEC, PUBMED_PROVIDER_MANIFEST),
    ),
)
def test_batch_one_specs_agree_with_their_governance_manifests(spec, manifest) -> None:
    assert validate_spec_manifest(spec, manifest) is spec


def test_arxiv_batch_one_spec_uses_the_verified_https_atom_endpoint() -> None:
    assert ARXIV_PROVIDER_SPEC.base_url == "https://export.arxiv.org/api"
    assert ARXIV_PROVIDER_SPEC.transport.protocol == "atom_xml"
    assert (
        validate_spec_manifest(PATENTSVIEW_REST_SPEC, PATENTSVIEW_PROVIDER_MANIFEST)
        is PATENTSVIEW_REST_SPEC
    )


@pytest.mark.parametrize(
    ("spec", "manifest", "update", "message"),
    [
        (ERIC_REST_SPEC, ERIC_PROVIDER_MANIFEST, {"provider_id": "other"}, "identity"),
        (ERIC_REST_SPEC, ERIC_PROVIDER_MANIFEST, {"adapter_id": "other-search"}, "adapter"),
        (ERIC_REST_SPEC, ERIC_PROVIDER_MANIFEST, {"host": "api.example.test"}, "host"),
        (
            ERIC_REST_SPEC,
            ERIC_PROVIDER_MANIFEST,
            {"configuration_keys": ("enabled",)},
            "configuration",
        ),
        (
            PATENTSVIEW_REST_SPEC,
            PATENTSVIEW_PROVIDER_MANIFEST,
            {
                "auth": AuthDeclaration(
                    placement="header", reference="OTHER_KEY", field_name="X-Key"
                )
            },
            "secret",
        ),
    ],
)
def test_spec_manifest_validation_fails_closed_on_each_contract_axis(
    spec: RestJsonProviderSpec,
    manifest,
    update: dict[str, object],
    message: str,
) -> None:
    mismatched = spec.model_copy(update=update)
    with pytest.raises(ValueError, match=message):
        validate_spec_manifest(mismatched, manifest)


@pytest.mark.parametrize(
    "domain",
    (
        "paper",
        "book",
        "research_output",
        "patent",
        "web",
        "news",
        "images",
        "videos",
        "social",
        "office",
        "developer",
        "cn_tech",
        "knowledge",
    ),
)
def test_spec_accepts_each_canonical_search_domain(domain: str) -> None:
    spec = RestJsonProviderSpec.model_validate(
        {
            **ERIC_REST_SPEC.model_dump(mode="python"),
            "provider_id": "domain-fixture",
            "domain": domain,
        }
    )
    assert spec.domain == domain


def test_legacy_spec_truthfully_declares_non_json_https_transport() -> None:
    spec = LegacySearchProviderSpec(
        provider_id="fixture",
        adapter_id="fixture-search",
        domain="paper",
        bridge_reason="Atom XML requires a reviewed client bridge",
        transport=LegacyTransportDeclaration(
            scheme="https",
            host="export.example.test",
            base_path="/api",
            protocol="atom_xml",
            operations=({"method": "GET", "endpoint": "/query"},),
        ),
        configuration_keys=("enabled",),
    )

    assert spec.base_url == "https://export.example.test/api"
    assert spec.adapter_kind == "legacy_bridge"
    assert spec.transport.protocol == "atom_xml"


def test_legacy_spec_rejects_unreviewed_transport_hosts() -> None:
    with pytest.raises(ValidationError):
        LegacySearchProviderSpec(
            provider_id="fixture",
            adapter_id="fixture-search",
            bridge_reason="fixture",
            transport={"scheme": "https", "host": "127.0.0.1", "protocol": "json"},
        )


def test_legacy_spec_declares_each_host_in_a_reviewed_multi_transport_flow() -> None:
    spec = LegacySearchProviderSpec(
        provider_id="fixture",
        adapter_id="fixture-search",
        bridge_reason="token exchange and API execution use different reviewed hosts",
        transport=LegacyTransportDeclaration(
            host="auth.example.test",
            protocol="json",
            operations=({"method": "POST", "endpoint": "/token"},),
        ),
        additional_transports=(
            LegacyTransportDeclaration(
                host="api.example.test",
                protocol="json",
                operations=({"method": "GET", "endpoint": "/search"},),
            ),
        ),
    )

    assert spec.hosts == ("auth.example.test", "api.example.test")
    with pytest.raises(ValidationError, match="hosts must be unique"):
        LegacySearchProviderSpec(
            provider_id="fixture",
            adapter_id="fixture-search",
            bridge_reason="duplicate host",
            transport=spec.transport,
            additional_transports=(spec.transport,),
        )


def test_auth_optional_flag_is_strict_and_cannot_be_string_coerced() -> None:
    with pytest.raises(ValidationError):
        AuthDeclaration(
            placement="query",
            reference="FIXTURE_TOKEN",
            field_name="token",
            required="false",
        )


def test_auth_declaration_resolves_multiple_credential_bindings_fail_closed() -> None:
    spec = LegacySearchProviderSpec(
        provider_id="fixture",
        adapter_id="fixture-search",
        bridge_reason="OAuth client credentials require two named runtime values",
        transport=LegacyTransportDeclaration(
            host="api.example.test",
            protocol="json",
            operations=({"method": "GET", "endpoint": "/search"},),
        ),
        auth=AuthDeclaration(
            placement="oauth_body",
            reference="FIXTURE_CLIENT_ID",
            field_name="client_id",
            additional_bindings=(
                CredentialBinding(
                    placement="oauth_body",
                    reference="FIXTURE_CLIENT_SECRET",
                    field_name="client_secret",
                ),
            ),
        ),
    )

    assert spec.auth_reference_requirements == (
        ("FIXTURE_CLIENT_ID", True),
        ("FIXTURE_CLIENT_SECRET", True),
    )
    assert resolve_provider_inputs(
        spec,
        {},
        {"FIXTURE_CLIENT_ID": " id ", "FIXTURE_CLIENT_SECRET": " secret "},
    ) == (
        {},
        {"FIXTURE_CLIENT_ID": "id", "FIXTURE_CLIENT_SECRET": "secret"},
    )
    with pytest.raises(ValueError, match="secret is unavailable"):
        resolve_provider_inputs(spec, {}, {"FIXTURE_CLIENT_ID": "id"})


def test_auth_declaration_rejects_duplicate_credential_references() -> None:
    with pytest.raises(ValidationError, match="references must be unique"):
        AuthDeclaration(
            placement="header",
            reference="FIXTURE_TOKEN",
            field_name="Authorization",
            additional_bindings=(
                CredentialBinding(
                    placement="query",
                    reference="FIXTURE_TOKEN",
                    field_name="token",
                ),
            ),
        )


@pytest.mark.asyncio
async def test_generic_spec_projects_nested_raw_json_without_inventing_source_fields() -> None:
    spec = RestJsonProviderSpec(
        provider_id="fixture",
        adapter_id="fixture-search",
        domain="web",
        host="api.example.test",
        response_mapping=SearchResponseMapping(
            items_field="response.items",
            total_field="response.total",
            identifier_path="id",
            identifier_pattern=r"[A-Za-z0-9-]+",
            identifier_scheme="fixture",
            title_path="title",
            record_url_path=None,
        ),
    )
    provider = RestJsonSearchProvider(
        _Client({"response": {"items": [{"id": "case-Sensitive", "title": "Raw"}], "total": 1}}),
        spec,
    )

    page = await provider.search(
        SearchRequest(query="raw", domains=("web",)),
        _context(),
        ExecutionContext.with_timeout(1),
    )

    assert page.items[0].id == "fixture:case-Sensitive"
    assert page.page.total == 1


@pytest.mark.parametrize("value", ["https://key@example.test", "bad host", "127.0.0.1"])
def test_spec_rejects_credential_urls_and_non_dns_hosts(value: str) -> None:
    with pytest.raises(ValidationError):
        RestJsonProviderSpec(provider_id="fixture", host=value)


@pytest.mark.parametrize(
    "fixed_fields",
    [
        {"api_key": "literal-canary"},
        {"redirect": "https://u:p@example.test"},
    ],
)
def test_request_mapping_rejects_secret_or_credential_bearing_fixed_fields(
    fixed_fields: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        SearchRequestMapping(
            query_field="query",
            limit_field="limit",
            fixed_fields=fixed_fields,
        )


def test_resolver_projects_only_declared_inputs_and_requires_named_secret() -> None:
    spec = RestJsonProviderSpec(
        provider_id="fixture",
        adapter_id="fixture-search",
        adapter_kind="legacy_bridge",
        review_status="bridge_exception",
        bridge_reason="fixture legacy mapping",
        host="api.example.test",
        auth={"placement": "header", "reference": "FIXTURE_TOKEN", "field_name": "X-Token"},
        configuration_keys=("enabled",),
    )
    assert resolve_provider_inputs(spec, {"enabled": True}, {"FIXTURE_TOKEN": " secret "}) == (
        {"enabled": True},
        {"FIXTURE_TOKEN": "secret"},
    )
    with pytest.raises(ValueError):
        resolve_provider_inputs(spec, {"other": True}, {"FIXTURE_TOKEN": "secret"})
    with pytest.raises(ValueError):
        resolve_provider_inputs(spec, {}, {"FIXTURE_TOKEN": " "})


@pytest.mark.asyncio
async def test_generic_factory_is_injectable_and_preserves_lifecycle_cancel_and_safe_errors() -> (
    None
):
    async def invoke(client, request, limit):
        return await client.search(request.query, limit=limit)

    provider = LegacySearchProvider(_Client(), LegacySearchSpec("fixture", "paper", invoke, _page))
    result = await provider.search(
        SearchRequest(query="q", domains=("paper",)), _context(), ExecutionContext.with_timeout(1)
    )
    assert result.items[0].id == "fixture:1"
    assert (await provider.probe(ExecutionContext.with_timeout(1))).status == "available"
    await provider.close()
    await provider.close()
    assert (await provider.probe(ExecutionContext.with_timeout(1))).status == "unavailable"

    blocked = LegacySearchProvider(
        _Client(RuntimeError("token=private")), LegacySearchSpec("fixture", "paper", invoke, _page)
    )
    with pytest.raises(ProviderError) as caught:
        await blocked.search(
            SearchRequest(query="q", domains=("paper",)),
            _context(),
            ExecutionContext.with_timeout(1),
        )
    assert caught.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert "private" not in str(caught.value)

    wait = asyncio.Event()

    async def slow(*_args, **_kwargs):
        await wait.wait()

    cancelled = LegacySearchProvider(_Client(), LegacySearchSpec("fixture", "paper", slow, _page))
    event = asyncio.Event()
    event.set()
    with pytest.raises(ProviderError) as cancellation:
        await cancelled.search(
            SearchRequest(query="q", domains=("paper",)),
            _context(),
            ExecutionContext.with_timeout(1, cancel_event=event),
        )
    assert cancellation.value.code is ProviderErrorCode.CANCELLED


@pytest.mark.asyncio
async def test_legacy_fetch_factory_preserves_typed_lifecycle_and_redaction() -> None:
    async def invoke(client, request):
        return await client.search(str(request.target))

    def project(_response, request, _context):
        content = "x" * 64
        return FetchResult(
            target=request.target,
            final_url=request.target,
            status="success",
            content=content,
            content_metadata=ContentMetadata(
                media_type="text/plain",
                retrieved_at=datetime.now(timezone.utc),
                truncated=False,
                content_length=len(content),
                quality="high",
            ),
            provenance=(Provenance(provider="fixture", attempt=1, outcome="success"),),
        )

    request = FetchTargetRequest(target="https://example.test/item")
    provider = LegacyFetchProvider(_Client(), LegacyFetchSpec("fixture", invoke, project))
    result = await provider.fetch(request, _context(), ExecutionContext.with_timeout(1))
    assert result.status == "success"
    assert (await provider.probe(ExecutionContext.with_timeout(1))).status == "available"
    await provider.close()
    await provider.close()

    failed = LegacyFetchProvider(
        _Client(RuntimeError("token=private")), LegacyFetchSpec("fixture", invoke, project)
    )
    with pytest.raises(ProviderError) as caught:
        await failed.fetch(request, _context(), ExecutionContext.with_timeout(1))
    assert caught.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert "private" not in str(caught.value)
