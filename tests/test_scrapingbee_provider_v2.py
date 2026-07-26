from __future__ import annotations
import pytest
from souwen.providers.runtime_clients.models import FetchResult as LegacyFetchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
)
from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.fetch_sources.scrapingbee import (
    SCRAPINGBEE_FETCH_PROFILE,
    SCRAPINGBEE_PROVIDER_MANIFEST,
    ScrapingBeeFetchProvider,
)
from souwen.providers.fetch_sources.scrapingbee import adapter


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
        source="scrapingbee",
        content="useful content",
        content_format="markdown",
    )


@pytest.mark.asyncio
async def test_scrapingbee_fetch_maps_safe_receipt_and_fails_closed(monkeypatch):
    monkeypatch.setattr(
        adapter, "validate_fetch_url", lambda url: (not url.endswith("/private"), "")
    )
    client = _Client(_receipt())
    result = await ScrapingBeeFetchProvider(client).fetch(
        FetchTargetRequest(target="https://1.1.1.1/page"),
        RequestContext(request_id="scrapingbee"),
        ExecutionContext.with_timeout(5),
    )
    assert (
        client.calls == [("https://1.1.1.1/page", 30.0)]
        and result.content_metadata.media_type == "text/markdown"
    )
    blocked = _Client(_receipt())
    with pytest.raises(ProviderError) as caught:
        await ScrapingBeeFetchProvider(blocked).fetch(
            FetchTargetRequest(target="https://1.1.1.1/private"),
            RequestContext(request_id="blocked"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.POLICY_BLOCKED and blocked.calls == []
    with pytest.raises(ProviderError) as caught:
        await ScrapingBeeFetchProvider(_Client(_receipt("https://1.1.1.1/private"))).fetch(
            FetchTargetRequest(target="https://1.1.1.1/page"),
            RequestContext(request_id="final"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


def test_scrapingbee_static_declarations_agree():
    assert (
        validate_spec_manifest(SCRAPINGBEE_FETCH_PROFILE, SCRAPINGBEE_PROVIDER_MANIFEST)
        is SCRAPINGBEE_FETCH_PROFILE
    )
    assert SCRAPINGBEE_PROVIDER_MANIFEST.secrets.references == ("SCRAPINGBEE_API_KEY",)
