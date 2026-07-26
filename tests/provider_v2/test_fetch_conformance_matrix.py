"""Nine-case matrix for source-specific Provider v2 Fetch specifications."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from souwen.models import FetchResult as LegacyFetchResult
from souwen.platform.provider_spi import FetchTargetRequest
from souwen.providers.fetch_sources.arxiv_fulltext import ArxivFulltextFetchProvider
from tests.support.provider_v2_conformance import (
    FETCH_CONFORMANCE_CASES,
    FetchConformanceDefinition,
    run_fetch_conformance_case,
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
)


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", FETCH_CONFORMANCE_CASES)
@pytest.mark.parametrize("definition", DEFINITIONS, ids=lambda item: item.provider_id)
async def test_fetch_provider_conformance_matrix(
    definition: FetchConformanceDefinition,
    case_id: str,
) -> None:
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
    inventory_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "internal"
        / "provider-migrations"
        / "b0-inventory.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    migrated_fetch_specs = {
        record["source_id"]
        for record in inventory["records"]
        if record["migration_status"] == "migrated"
        and record["target_capability"] == "fetch"
        and record["target_spec_identity"] is not None
    }

    assert {definition.provider_id for definition in DEFINITIONS} == migrated_fetch_specs
