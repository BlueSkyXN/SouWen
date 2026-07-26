"""Provider-specific request bounds for Batch 4 book catalog bridges."""

from __future__ import annotations

import pytest

from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.doab import DOABSearchProvider
from souwen.providers.information_sources.librivox import LibriVoxSearchProvider
from souwen.providers.information_sources.oapen import OAPENSearchProvider
from souwen.providers.information_sources.wikisource import WikisourceSearchProvider


class _UnexpectedClient:
    def __init__(self) -> None:
        self.called = False

    async def search(self, *_args, **_kwargs):
        self.called = True
        raise AssertionError("out-of-range request must not reach the legacy client")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_type", "limit"),
    (
        (DOABSearchProvider, 26),
        (OAPENSearchProvider, 26),
        (LibriVoxSearchProvider, 51),
        (WikisourceSearchProvider, 21),
    ),
)
async def test_source_limit_above_legacy_contract_is_rejected_as_invalid_request(
    provider_type: type,
    limit: int,
) -> None:
    client = _UnexpectedClient()
    provider = provider_type(client)

    with pytest.raises(ProviderError) as caught:
        await provider.search(
            SearchRequest(
                query="catalog",
                domains=("book",),
                page=SearchPageRequest(limit=limit),
            ),
            RequestContext(request_id=f"limit-{limit}"),
            ExecutionContext.with_timeout(1),
        )

    assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
    assert client.called is False
