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
from souwen.providers.fetch_sources.deepwiki import (
    DEEPWIKI_FETCH_PROFILE,
    DEEPWIKI_PROVIDER_MANIFEST,
    DeepWikiFetchProvider,
)
from souwen.providers.fetch_sources.deepwiki import adapter


class _Client:
    def __init__(self, result):
        self.result, self.calls = result, []

    async def fetch(self, url_or_shorthand, max_depth=1, mode="aggregate", timeout=60.0):
        self.calls.append((url_or_shorthand, max_depth, mode, timeout))
        return self.result


def _receipt(final_url="https://deepwiki.com/owner/repo"):
    return LegacyFetchResult(
        url="https://deepwiki.com/owner/repo",
        final_url=final_url,
        source="deepwiki",
        content="useful content",
        content_format="markdown",
    )


@pytest.mark.asyncio
async def test_deepwiki_fetch_only_accepts_bounded_repository_targets(monkeypatch):
    monkeypatch.setattr(
        adapter, "validate_fetch_url", lambda url: (url != "https://deepwiki.com/owner/private", "")
    )
    client = _Client(_receipt())
    result = await DeepWikiFetchProvider(client).fetch(
        FetchTargetRequest(target="https://github.com/owner/repo"),
        RequestContext(request_id="deepwiki"),
        ExecutionContext.with_timeout(5),
    )
    assert (
        client.calls == [("owner/repo", 0, "aggregate", 30.0)]
        and result.content_metadata.media_type == "text/markdown"
    )
    direct = _Client(_receipt())
    await DeepWikiFetchProvider(direct).fetch(
        FetchTargetRequest(target="https://deepwiki.com/owner/repo"),
        RequestContext(request_id="deepwiki-direct"),
        ExecutionContext.with_timeout(5),
    )
    assert direct.calls == [("owner/repo", 0, "aggregate", 30.0)]
    blocked = _Client(_receipt())
    with pytest.raises(ProviderError) as caught:
        await DeepWikiFetchProvider(blocked).fetch(
            FetchTargetRequest(target="https://example.com/owner/repo"),
            RequestContext(request_id="blocked"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.POLICY_BLOCKED and blocked.calls == []
    with pytest.raises(ProviderError) as caught:
        await DeepWikiFetchProvider(_Client(_receipt("https://deepwiki.com/owner/private"))).fetch(
            FetchTargetRequest(target="https://deepwiki.com/owner/repo"),
            RequestContext(request_id="final"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


def test_deepwiki_static_declarations_agree():
    assert (
        validate_spec_manifest(DEEPWIKI_FETCH_PROFILE, DEEPWIKI_PROVIDER_MANIFEST)
        is DEEPWIKI_FETCH_PROFILE
    )
    assert DEEPWIKI_PROVIDER_MANIFEST.secrets.references == ()
    assert DEEPWIKI_PROVIDER_MANIFEST.secrets.optional_references == ("JINA_API_KEY",)
    assert DEEPWIKI_FETCH_PROFILE.hosts == ("deepwiki.com", "r.jina.ai")
    assert DEEPWIKI_FETCH_PROFILE.additional_transports[0].operations[0].endpoint == "/:target"
