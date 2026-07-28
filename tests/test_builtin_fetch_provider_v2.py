"""Deterministic P4-04 builtin Fetch Provider conformance."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from souwen.providers.runtime_clients.models import FetchResult as LegacyFetchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchContentOptions,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
)
from souwen.providers.fetch_sources.builtin import BUILTIN_FETCH_MANIFEST, BuiltinFetchProvider


class _Client:
    def __init__(self, result: LegacyFetchResult) -> None:
        self.result = result
        self.calls = []
        self.closed = 0

    async def fetch(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.result

    async def close(self):
        self.closed += 1


def _legacy_result(content: str = "Useful canonical content") -> LegacyFetchResult:
    return LegacyFetchResult(
        url="https://example.com/page",
        final_url="https://example.com/final",
        title="Example",
        content=content,
        content_format="text",
        source="builtin",
        raw={
            "provider": "builtin",
            "media_type": "text/plain",
            "charset": "utf-8",
            "content_length_bytes": len(content.encode()),
        },
    )


@pytest.mark.asyncio
async def test_provider_maps_safe_receipt_and_preserves_low_quality_partial_signal() -> None:
    client = _Client(_legacy_result("short"))
    provider = BuiltinFetchProvider(
        client,
        clock=lambda: datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    result = await provider.fetch(
        FetchTargetRequest(
            target="https://example.com/page",
            content=FetchContentOptions(max_code_points=321),
        ),
        RequestContext(request_id="builtin-v2"),
        ExecutionContext.with_timeout(5),
    )

    assert result.status == "success"
    assert result.content == "short"
    assert result.content_metadata is not None
    assert result.content_metadata.quality == "low"
    assert result.content_metadata.media_type == "text/plain"
    assert client.calls[0][1]["max_length"] == 321
    assert client.calls[0][1]["enforce_target_contract"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_error_code", "expected"),
    [
        ("policy_blocked", ProviderErrorCode.POLICY_BLOCKED),
        ("response_too_large", ProviderErrorCode.PAYLOAD_TOO_LARGE),
        ("unsupported_media_type", ProviderErrorCode.UNSUPPORTED_MEDIA_TYPE),
        ("empty_content", ProviderErrorCode.INVALID_UPSTREAM_RESPONSE),
    ],
)
async def test_provider_maps_target_receipt_failures_without_raw_detail(
    target_error_code: str,
    expected: ProviderErrorCode,
) -> None:
    client = _Client(
        LegacyFetchResult(
            url="https://example.com/page",
            final_url="https://example.com/page",
            source="builtin",
            error="raw private upstream detail",
            raw={"target_error_code": target_error_code},
        )
    )
    provider = BuiltinFetchProvider(client)

    with pytest.raises(ProviderError) as caught:
        await provider.fetch(
            FetchTargetRequest(target="https://example.com/page"),
            RequestContext(request_id="builtin-v2"),
            ExecutionContext.with_timeout(5),
        )

    assert caught.value.code is expected
    assert "private" not in str(caught.value)


@pytest.mark.asyncio
async def test_probe_and_close_are_local_and_idempotent() -> None:
    client = _Client(_legacy_result())
    provider = BuiltinFetchProvider(client)

    assert (await provider.probe(ExecutionContext.with_timeout(5))).status == "available"
    await provider.close()
    await provider.close()

    assert client.calls == []
    assert client.closed == 1
    assert (await provider.probe(ExecutionContext.with_timeout(5))).status == "unavailable"


def test_builtin_manifest_is_anonymous_zero_cost_fetch_only() -> None:
    assert BUILTIN_FETCH_MANIFEST.version == "2.0.0rc3"
    assert BUILTIN_FETCH_MANIFEST.capabilities == ("fetch",)
    assert BUILTIN_FETCH_MANIFEST.secrets.references == ()
    assert BUILTIN_FETCH_MANIFEST.risk.authenticated is False
    assert BUILTIN_FETCH_MANIFEST.risk.costed is False
