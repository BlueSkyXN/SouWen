"""End-to-end in-process P4-03 vertical using a deterministic fake gateway."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from souwen.config import SouWenConfig
from souwen.modules.llm_search.application import LLMSearchModuleService
from souwen.platform.provider_manager import ProviderManager
from souwen.platform.provider_spi import (
    ExecutionContext,
    LLMSearchRequest,
    ProviderRef,
    RequestContext,
)
from souwen.providers.llm_sources.uniapi_ark_annotations.adapter import (
    UniApiArkAnnotationsDeepSeekProvider,
)
from souwen.providers.llm_sources.uniapi_ark_annotations.manifest import (
    DEEPSEEK_ADAPTER_ID,
    UNIAPI_ARK_MANIFESTS,
)


class _Response:
    def json(self):
        return {
            "status": "completed",
            "model": "deepseek-v3-2-251201",
            "output": [
                {"type": "web_search_call", "status": "completed"},
                {
                    "type": "message",
                    "status": "completed",
                    "message": {
                        "content": [
                            {
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "title": "Vertical fixture",
                                        "url": "https://example.com/vertical",
                                    }
                                ]
                            }
                        ]
                    },
                },
            ],
            "usage": {},
        }


class _Gateway:
    def __init__(self) -> None:
        self.calls = 0

    async def post(self, *args, **kwargs):
        self.calls += 1
        return _Response()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_config_to_manager_to_module_to_provider_vertical() -> None:
    config = SouWenConfig(
        sources={DEEPSEEK_ADAPTER_ID: {"enabled": True}},
        llm_search_gateways={
            "uniapi": {
                "api_key": "fixture-secret",
                "base_url": "https://gateway.example.test",
            }
        },
    )
    selected = config.enabled_uniapi_ark_source_ids()[0]
    gateway = _Gateway()

    def resolve_config(manifest):
        if manifest.id != selected:
            raise ValueError("adapter is disabled")
        source = config.get_source_config(selected)
        return {
            "enabled": True,
            "max_keyword": source.params.get("max_keyword", 10),
            "timeout_seconds": source.timeout or 45,
        }

    def resolve_secrets(_manifest, _references):
        uniapi = config.get_llm_search_gateway("uniapi")
        return {
            "UNIAPI_API_KEY": uniapi.api_key or "",
            "UNIAPI_BASE_URL": uniapi.base_url or "",
        }

    manager = ProviderManager(
        config_resolver=resolve_config,
        secret_resolver=resolve_secrets,
    )

    def factory(configuration, secrets):
        return UniApiArkAnnotationsDeepSeekProvider(
            configuration,
            secrets,
            transport=gateway,
            clock=lambda: datetime(2026, 7, 24, tzinfo=timezone.utc),
        )

    manager.register_factory(
        package_id=selected,
        export="UniApiArkAnnotationsDeepSeekProvider",
        factory=factory,
        provider_type=UniApiArkAnnotationsDeepSeekProvider,
    )
    registrations = manager.discover(UNIAPI_ARK_MANIFESTS)

    assert tuple(registration.accepted for registration in registrations) == (True, True)
    assert manager.eligible_adapter_ids == (selected,)
    assert manager.diagnostics[-1].reason_code == "factory_missing"

    result = await LLMSearchModuleService(manager, selected).search(
        LLMSearchRequest(
            query="vertical query",
            providers=(ProviderRef(id=selected, kind="llm_search"),),
            strategy="single",
        ),
        RequestContext(request_id="vertical-v2"),
        ExecutionContext.with_timeout(5),
    )

    assert result.items[0].title == "Vertical fixture"
    assert result.evidence[0].item_id == result.items[0].id
    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None
    assert gateway.calls == 1


def test_enabled_uniapi_without_gateway_is_provider_local_unavailable() -> None:
    config = SouWenConfig(sources={DEEPSEEK_ADAPTER_ID: {"enabled": True}})
    manager = ProviderManager(
        config_resolver=lambda manifest: (
            {"enabled": True}
            if manifest.id == DEEPSEEK_ADAPTER_ID
            else (_ for _ in ()).throw(ValueError("adapter is disabled"))
        ),
        secret_resolver=lambda _manifest, _references: {},
    )
    manager.register_factory(
        package_id=DEEPSEEK_ADAPTER_ID,
        export="UniApiArkAnnotationsDeepSeekProvider",
        factory=UniApiArkAnnotationsDeepSeekProvider,
        provider_type=UniApiArkAnnotationsDeepSeekProvider,
    )

    manager.discover(UNIAPI_ARK_MANIFESTS)

    assert config.missing_uniapi_gateway_fields() == (
        "llm_search_gateways.uniapi.api_key",
        "llm_search_gateways.uniapi.base_url",
    )
    assert manager.eligible_adapter_ids == ()
    assert {diagnostic.reason_code for diagnostic in manager.diagnostics} == {
        "secret_unavailable",
        "factory_missing",
    }
