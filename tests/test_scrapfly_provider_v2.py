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
from souwen.providers.fetch_sources.scrapfly import (
    SCRAPFLY_FETCH_PROFILE,
    SCRAPFLY_PROVIDER_MANIFEST,
    ScrapflyFetchProvider,
)
from souwen.providers.fetch_sources.scrapfly import adapter


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
        source="scrapfly",
        content="useful content",
        content_format="markdown",
    )


@pytest.mark.asyncio
async def test_scrapfly_fetch_maps_safe_receipt_and_fails_closed(monkeypatch):
    monkeypatch.setattr(
        adapter, "validate_fetch_url", lambda url: (not url.endswith("/private"), "")
    )
    client = _Client(_receipt())
    result = await ScrapflyFetchProvider(client).fetch(
        FetchTargetRequest(target="https://1.1.1.1/page"),
        RequestContext(request_id="scrapfly"),
        ExecutionContext.with_timeout(5),
    )
    assert (
        client.calls == [("https://1.1.1.1/page", 30.0)]
        and result.content_metadata.media_type == "text/markdown"
    )
    blocked = _Client(_receipt())
    with pytest.raises(ProviderError) as caught:
        await ScrapflyFetchProvider(blocked).fetch(
            FetchTargetRequest(target="https://1.1.1.1/private"),
            RequestContext(request_id="blocked"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.POLICY_BLOCKED and blocked.calls == []
    with pytest.raises(ProviderError) as caught:
        await ScrapflyFetchProvider(_Client(_receipt("https://1.1.1.1/private"))).fetch(
            FetchTargetRequest(target="https://1.1.1.1/page"),
            RequestContext(request_id="final"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


def test_scrapfly_static_declarations_agree():
    assert (
        validate_spec_manifest(SCRAPFLY_FETCH_PROFILE, SCRAPFLY_PROVIDER_MANIFEST)
        is SCRAPFLY_FETCH_PROFILE
    )
    assert SCRAPFLY_PROVIDER_MANIFEST.secrets.references == ("SCRAPFLY_API_KEY",)
