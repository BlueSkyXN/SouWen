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
from souwen.providers.fetch_sources.jina_reader import (
    JINA_READER_FETCH_PROFILE,
    JINA_READER_PROVIDER_MANIFEST,
    JinaReaderFetchProvider,
)
from souwen.providers.fetch_sources.jina_reader import adapter


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
        source="jina_reader",
        content="useful content",
        content_format="markdown",
    )


@pytest.mark.asyncio
async def test_jina_reader_fetch_maps_safe_receipt_and_fails_closed(monkeypatch):
    monkeypatch.setattr(
        adapter, "validate_fetch_url", lambda url: (not url.endswith("/private"), "")
    )
    client = _Client(_receipt())
    result = await JinaReaderFetchProvider(client).fetch(
        FetchTargetRequest(target="https://1.1.1.1/page"),
        RequestContext(request_id="jina"),
        ExecutionContext.with_timeout(5),
    )
    assert (
        client.calls == [("https://1.1.1.1/page", 30.0)]
        and result.content_metadata.media_type == "text/markdown"
    )
    blocked = _Client(_receipt())
    with pytest.raises(ProviderError) as caught:
        await JinaReaderFetchProvider(blocked).fetch(
            FetchTargetRequest(target="https://1.1.1.1/private"),
            RequestContext(request_id="blocked"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.POLICY_BLOCKED and blocked.calls == []
    with pytest.raises(ProviderError) as caught:
        await JinaReaderFetchProvider(_Client(_receipt("https://1.1.1.1/private"))).fetch(
            FetchTargetRequest(target="https://1.1.1.1/page"),
            RequestContext(request_id="final"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


def test_jina_reader_static_declarations_agree():
    assert (
        validate_spec_manifest(JINA_READER_FETCH_PROFILE, JINA_READER_PROVIDER_MANIFEST)
        is JINA_READER_FETCH_PROFILE
    )
    assert JINA_READER_PROVIDER_MANIFEST.secrets.optional_references == ("JINA_API_KEY",)
