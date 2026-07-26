"""P4-04 Module to Manager to builtin Provider deterministic vertical."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from souwen.providers.runtime_clients.models import FetchResult as LegacyFetchResult
from souwen.modules.fetch.application import FetchModuleService
from souwen.platform.provider_manager import ProviderManager
from souwen.platform.provider_spi import ExecutionContext, FetchRequest, RequestContext
from souwen.providers.fetch_sources.builtin import BUILTIN_FETCH_MANIFEST, BuiltinFetchProvider


class _Client:
    async def fetch(self, url, **kwargs):
        return LegacyFetchResult(
            url=url,
            final_url=url,
            content="vertical canonical content " * 4,
            content_format="text",
            source="builtin",
            raw={
                "provider": "builtin",
                "media_type": "application/json",
                "charset": "utf-8",
                "content_length_bytes": 128,
            },
        )

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_module_manager_provider_vertical() -> None:
    manager = ProviderManager(config_resolver=lambda _manifest: {"enabled": True})
    client = _Client()

    def factory(_configuration, _secrets):
        return BuiltinFetchProvider(
            client,
            clock=lambda: datetime(2026, 7, 24, tzinfo=timezone.utc),
        )

    manager.register_factory(
        package_id="builtin-fetch",
        export="BuiltinFetchProvider",
        factory=factory,
        provider_type=BuiltinFetchProvider,
    )
    assert manager.discover([BUILTIN_FETCH_MANIFEST])[0].accepted is True

    batch = await FetchModuleService(manager).fetch(
        FetchRequest(targets=("https://example.com/a", "https://example.com/b")),
        RequestContext(request_id="builtin-vertical-v2"),
        ExecutionContext.with_timeout(5),
    )

    assert [item.status for item in batch.items] == ["success", "success"]
    assert all(item.content_metadata.media_type == "application/json" for item in batch.items)
    assert batch.meta.partial is False
