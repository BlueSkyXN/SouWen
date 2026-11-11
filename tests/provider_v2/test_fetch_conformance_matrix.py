"""Nine-case matrix for source-specific Provider v2 Fetch specifications."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from souwen.providers.runtime_clients.models import FetchResult as LegacyFetchResult
from souwen.platform.provider_spi import FetchTargetRequest
from souwen.providers.catalog import builtin_provider_manifests
from souwen.providers.fetch_sources.arxiv_fulltext import ArxivFulltextFetchProvider
from souwen.providers.fetch_sources.deepwiki import DeepWikiFetchProvider
from souwen.providers.fetch_sources.deepwiki import adapter as deepwiki_adapter
from souwen.providers.fetch_sources.jina_reader import JinaReaderFetchProvider
from souwen.providers.fetch_sources.jina_reader import adapter as jina_reader_adapter
from souwen.providers.fetch_sources.newspaper import NewspaperFetchProvider
from souwen.providers.fetch_sources.readability import ReadabilityFetchProvider
from souwen.platform.provider_spec import public_fetch
from souwen.providers.fetch_sources.wayback import WaybackFetchProvider
from souwen.providers.fetch_sources.wayback import adapter as wayback_adapter
from tests.support.provider_v2_conformance import (
    FETCH_CONFORMANCE_CASES,
    FetchConformanceDefinition,
    run_fetch_conformance_case,
)


def _batch_three_definition(provider_id: str, provider_type: type) -> FetchConformanceDefinition:
    target = (
        "https://deepwiki.com/owner/repo" if provider_id == "deepwiki" else "https://1.1.1.1/page"
    )
    blocked_target = (
        "https://example.com/owner/repo"
        if provider_id == "deepwiki"
        else "http://127.0.0.1/private"
    )
    return FetchConformanceDefinition(
        provider_id=provider_id,
        build_provider=lambda client, enabled: provider_type(client, enabled=enabled),
        request=FetchTargetRequest(target=target),
        blocked_request=FetchTargetRequest(target=blocked_target),
        success_response=LegacyFetchResult(
            url=target,
            final_url=target,
            source=provider_id,
            title="Conformance fixture",
            content="Deterministic Fetch content for Provider v2 conformance.",
            content_format="markdown",
        ),
        empty_response=SimpleNamespace(source=provider_id, error=None, content=""),
        invalid_response=object(),
    )


DEFINITIONS = (
    FetchConformanceDefinition(
        provider_id="arxiv_fulltext",
        build_provider=lambda client, enabled: ArxivFulltextFetchProvider(client, enabled=enabled),
        request=FetchTargetRequest(target="https://arxiv.org/abs/2601.00001"),
        blocked_request=FetchTargetRequest(target="https://example.test/abs/2601.00001"),
        success_response=LegacyFetchResult(
            url="https://arxiv.org/abs/2601.00001",
            final_url="https://arxiv.org/html/2601.00001",
            source="arxiv_fulltext",
            title="Conformance fixture",
            content="Deterministic arXiv full text for Provider v2 conformance.",
            content_format="text",
        ),
        empty_response=SimpleNamespace(source="arxiv_fulltext", error=None, content=""),
        invalid_response=object(),
    ),
    *(
        _batch_three_definition(provider_id, provider_type)
        for provider_id, provider_type in (
            ("deepwiki", DeepWikiFetchProvider),
            ("jina_reader", JinaReaderFetchProvider),
            ("newspaper", NewspaperFetchProvider),
            ("readability", ReadabilityFetchProvider),
            ("wayback", WaybackFetchProvider),
        )
    ),
)

_VALIDATOR_MODULES = {
    "deepwiki": deepwiki_adapter,
    "jina_reader": jina_reader_adapter,
    "newspaper": public_fetch,
    "readability": public_fetch,
    "wayback": wayback_adapter,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", FETCH_CONFORMANCE_CASES)
@pytest.mark.parametrize("definition", DEFINITIONS, ids=lambda item: item.provider_id)
async def test_fetch_provider_conformance_matrix(
    definition: FetchConformanceDefinition,
    case_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator_module = _VALIDATOR_MODULES.get(definition.provider_id)
    if validator_module is not None:
        monkeypatch.setattr(
            validator_module,
            "validate_fetch_url",
            lambda url: (not str(url).startswith("http://127.0.0.1"), "fixture-policy"),
        )
    await run_fetch_conformance_case(definition, case_id)


def test_each_source_specific_fetch_provider_declares_the_stable_cases() -> None:
    assert FETCH_CONFORMANCE_CASES == (
        "success",
        "empty",
        "invalid_config",
        "cancellation",
        "rate_limit",
        "invalid_upstream",
        "policy_blocked",
        "probe_close",
        "redaction",
    )
    migrated_fetch_specs = {
        manifest.id
        for manifest in builtin_provider_manifests()
        if "fetch" in manifest.capabilities and manifest.id != "builtin-fetch"
    }

    assert {definition.provider_id for definition in DEFINITIONS} == migrated_fetch_specs
