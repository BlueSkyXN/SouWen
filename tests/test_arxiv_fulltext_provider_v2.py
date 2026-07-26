from __future__ import annotations

import pytest

from souwen.models import FetchResult as LegacyFetchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
)
from souwen.providers.fetch_sources.arxiv_fulltext import (
    ARXIV_FULLTEXT_FETCH_PROFILE,
    ARXIV_FULLTEXT_PROVIDER_MANIFEST,
    ArxivFulltextFetchProvider,
)


class _Client:
    def __init__(self, result):
        self.result, self.calls, self.closed = result, [], 0

    async def get_fulltext(self, paper_id):
        self.calls.append(paper_id)
        return self.result

    async def close(self):
        self.closed += 1


@pytest.mark.asyncio
async def test_arxiv_fetch_bridge_only_accepts_reviewed_publication_targets() -> None:
    client = _Client(
        LegacyFetchResult(
            url="https://arxiv.org/abs/2401.00001",
            final_url="https://arxiv.org/html/2401.00001",
            source="arxiv_fulltext",
            title="Fixture",
            content="Useful full text",
            content_format="text",
        )
    )
    provider = ArxivFulltextFetchProvider(client)
    result = await provider.fetch(
        FetchTargetRequest(target="https://arxiv.org/abs/2401.00001"),
        RequestContext(request_id="arxiv"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == ["2401.00001"]
    assert result.status == "success" and result.content_metadata.media_type == "text/plain"
    assert ARXIV_FULLTEXT_FETCH_PROFILE.target_contract == "arxiv_publication_url"
    assert ARXIV_FULLTEXT_PROVIDER_MANIFEST.capabilities == ("fetch",)


@pytest.mark.asyncio
async def test_arxiv_fetch_bridge_blocks_non_arxiv_target_without_client_call() -> None:
    client = _Client(None)
    provider = ArxivFulltextFetchProvider(client)
    with pytest.raises(ProviderError) as caught:
        await provider.fetch(
            FetchTargetRequest(target="https://example.com/abs/2401.00001"),
            RequestContext(request_id="arxiv"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.POLICY_BLOCKED
    assert client.calls == []


@pytest.mark.asyncio
async def test_arxiv_fetch_bridge_accepts_legacy_archive_identifiers() -> None:
    client = _Client(
        LegacyFetchResult(
            url="https://arxiv.org/abs/hep-th/9901001v2",
            final_url="https://arxiv.org/html/hep-th/9901001v2",
            source="arxiv_fulltext",
            content="Legacy identifier full text",
            content_format="text",
        )
    )

    await ArxivFulltextFetchProvider(client).fetch(
        FetchTargetRequest(target="https://arxiv.org/abs/hep-th/9901001v2"),
        RequestContext(request_id="arxiv-legacy"),
        ExecutionContext.with_timeout(5),
    )

    assert client.calls == ["hep-th/9901001v2"]
