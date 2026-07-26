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
from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.fetch_sources.cloudflare import (
    CLOUDFLARE_FETCH_PROFILE,
    CLOUDFLARE_PROVIDER_MANIFEST,
    CloudflareFetchProvider,
)
from souwen.providers.fetch_sources.cloudflare import adapter


class _Client:
    def __init__(self, result):
        self.result, self.calls = result, []

    async def fetch(self, url, timeout=30.0):
        self.calls.append((url, timeout))
        return self.result


def _receipt(final_url="https://1.1.1.1/final"):
    return LegacyFetchResult(
        url="https://1.1.1.1/page",
        final_url=final_url,
        source="cloudflare",
        content="useful content",
        content_format="markdown",
    )


@pytest.mark.asyncio
async def test_cloudflare_fetch_maps_safe_receipt_and_fails_closed(monkeypatch):
    monkeypatch.setattr(
        adapter, "validate_fetch_url", lambda url: (not url.endswith("/private"), "")
    )
    client = _Client(_receipt())
    result = await CloudflareFetchProvider(client).fetch(
        FetchTargetRequest(target="https://1.1.1.1/page"),
        RequestContext(request_id="cloudflare"),
        ExecutionContext.with_timeout(5),
    )
    assert (
        client.calls == [("https://1.1.1.1/page", 30.0)]
        and result.content_metadata.media_type == "text/markdown"
    )
    blocked = _Client(_receipt())
    with pytest.raises(ProviderError) as caught:
        await CloudflareFetchProvider(blocked).fetch(
            FetchTargetRequest(target="https://1.1.1.1/private"),
            RequestContext(request_id="blocked"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.POLICY_BLOCKED and blocked.calls == []
    with pytest.raises(ProviderError) as caught:
        await CloudflareFetchProvider(_Client(_receipt("https://1.1.1.1/private"))).fetch(
            FetchTargetRequest(target="https://1.1.1.1/page"),
            RequestContext(request_id="final"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


def test_cloudflare_static_declarations_agree():
    assert (
        validate_spec_manifest(CLOUDFLARE_FETCH_PROFILE, CLOUDFLARE_PROVIDER_MANIFEST)
        is CLOUDFLARE_FETCH_PROFILE
    )
    assert CLOUDFLARE_PROVIDER_MANIFEST.secrets.references == (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
    )
