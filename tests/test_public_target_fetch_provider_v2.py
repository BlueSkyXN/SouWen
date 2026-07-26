from __future__ import annotations

import pytest

from souwen.providers.runtime_clients.models import FetchResult as LegacyFetchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchContentOptions,
    FetchPolicyOptions,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
)
from souwen.platform.provider_spec import validate_spec_manifest
from souwen.platform.provider_spec import public_fetch
from souwen.providers.fetch_sources.newspaper import (
    NEWSPAPER_FETCH_PROFILE,
    NEWSPAPER_PROVIDER_MANIFEST,
    NewspaperFetchProvider,
)
from souwen.providers.fetch_sources.readability import (
    READABILITY_FETCH_PROFILE,
    READABILITY_PROVIDER_MANIFEST,
    ReadabilityFetchProvider,
)


class _Client:
    def __init__(self, source: str) -> None:
        self.source, self.calls = source, []

    async def fetch(self, url: str, timeout: float = 30.0) -> LegacyFetchResult:
        self.calls.append((url, timeout))
        return LegacyFetchResult(
            url=url,
            final_url="https://1.1.1.1/final",
            source=self.source,
            title="title",
            content="useful content",
            content_format="markdown",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_type", "provider_id"),
    ((NewspaperFetchProvider, "newspaper"), (ReadabilityFetchProvider, "readability")),
)
async def test_public_target_fetch_projects_truncates_and_rejects_policy(
    monkeypatch, provider_type, provider_id
) -> None:
    monkeypatch.setattr(
        public_fetch, "validate_fetch_url", lambda url: (not url.endswith("/private"), "")
    )
    client = _Client(provider_id)
    result = await provider_type(client).fetch(
        FetchTargetRequest(
            target="https://1.1.1.1/page",
            content=FetchContentOptions(max_code_points=6),
        ),
        RequestContext(request_id=provider_id),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("https://1.1.1.1/page", 30.0)]
    assert result.content == "useful"
    assert result.content_metadata is not None and result.content_metadata.truncated is True

    blocked = _Client(provider_id)
    with pytest.raises(ProviderError) as caught:
        await provider_type(blocked).fetch(
            FetchTargetRequest(target="https://1.1.1.1/private"),
            RequestContext(request_id="blocked"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.POLICY_BLOCKED
    assert blocked.calls == []

    with pytest.raises(ProviderError) as caught:
        await provider_type(_Client(provider_id)).fetch(
            FetchTargetRequest(
                target="https://1.1.1.1/page",
                policy=FetchPolicyOptions(respect_robots=True),
            ),
            RequestContext(request_id="robots"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_REQUEST


def test_public_target_specs_match_manifests() -> None:
    for spec, manifest in (
        (NEWSPAPER_FETCH_PROFILE, NEWSPAPER_PROVIDER_MANIFEST),
        (READABILITY_FETCH_PROFILE, READABILITY_PROVIDER_MANIFEST),
    ):
        assert validate_spec_manifest(spec, manifest) is spec
        assert manifest.network.egress_hosts == ()
        assert manifest.network.target_egress == "validated_public_target"
