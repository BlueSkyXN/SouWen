"""Deterministic tests for the pre-mutation HFS LLM Search live gate."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest
import yaml

from scripts import hf_space_llm_preflight as preflight
from souwen.platform.provider_spi import ProviderError, ProviderErrorCode


DEEPSEEK_ID = "uniapi_ark_annotations_deepseek_v3_2_251201"
DOUBAO_ID = "uniapi_ark_annotations_doubao_seed_2_0_lite_260428"


def _encoded_config(
    *,
    deepseek: bool,
    doubao: bool,
    api_key: str = "${UNIAPI_API_KEY}",
    base_url: str = "https://gateway.example.invalid/v1",
) -> str:
    payload = {
        "llm_search_gateways": {
            "uniapi": {
                "api_key": api_key,
                "base_url": base_url,
            }
        },
        "sources": {
            DEEPSEEK_ID: {"enabled": deepseek},
            DOUBAO_ID: {"enabled": doubao},
        },
    }
    return base64.b64encode(yaml.safe_dump(payload).encode()).decode()


def test_load_preflight_config_resolves_exact_gateway_references_without_env_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UNIAPI_API_KEY", raising=False)
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "runner-token-canary")
    monkeypatch.setenv(
        "SOUWEN_LLM_SEARCH_GATEWAYS",
        '{"uniapi":{"api_key":"runner-override","base_url":"https://override.invalid"}}',
    )

    config = preflight.load_preflight_config(
        _encoded_config(deepseek=False, doubao=True),
        "secret-canary",
    )

    assert config.enabled_uniapi_ark_source_ids() == (DOUBAO_ID,)
    gateway = config.get_llm_search_gateway("uniapi")
    assert gateway.api_key == "secret-canary"
    assert gateway.base_url == "https://gateway.example.invalid/v1"
    assert "UNIAPI_API_KEY" not in preflight.os.environ
    assert preflight.os.environ["ACTIONS_RUNTIME_TOKEN"] == "runner-token-canary"
    assert "runner-override" not in repr(gateway)

    with pytest.raises(preflight.PreflightFailure, match="configuration"):
        preflight.load_preflight_config(
            _encoded_config(deepseek=True, doubao=True),
            "secret-canary",
        )


@pytest.mark.parametrize(
    ("api_key", "base_url"),
    [
        ("${ACTIONS_RUNTIME_TOKEN}", "https://gateway.example.invalid/v1"),
        ("${HOME}", "https://gateway.example.invalid/v1"),
        ("${UNIAPI_API_KEY}", "${ACTIONS_RUNTIME_URL}"),
    ],
)
def test_load_preflight_config_rejects_unmanaged_runner_environment_references(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str,
    base_url: str,
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "runner-token-canary")
    monkeypatch.setenv("ACTIONS_RUNTIME_URL", "https://runner-canary.invalid")

    with pytest.raises(preflight.PreflightFailure) as exc_info:
        preflight.load_preflight_config(
            _encoded_config(
                deepseek=False,
                doubao=True,
                api_key=api_key,
                base_url=base_url,
            ),
            "managed-api-key",
        )

    assert "runner-token-canary" not in str(exc_info.value)
    assert "runner-canary" not in str(exc_info.value)


class _Service:
    def __init__(self, *, error: ProviderError | None = None) -> None:
        self.error = error
        self.calls = []

    async def search(self, request, context, execution):
        self.calls.append((request, context, execution))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(evidence=(object(),))


class _CancelledService(_Service):
    async def search(self, request, context, execution):
        self.calls.append((request, context, execution))
        raise preflight.asyncio.CancelledError


class _Runtime:
    def __init__(self, service: _Service) -> None:
        self.services = SimpleNamespace(llm_search=service)
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1


class _Config:
    def __init__(self, selected: tuple[str, ...]) -> None:
        self.selected = selected

    def enabled_uniapi_ark_source_ids(self) -> tuple[str, ...]:
        return self.selected


@pytest.mark.asyncio
async def test_preflight_uses_only_explicit_provider_and_closes_runtime() -> None:
    service = _Service()
    runtime = _Runtime(service)

    receipt = await preflight.run_preflight(
        _Config((DOUBAO_ID,)),
        runtime_factory=lambda _config: runtime,
        timeout_seconds=7,
    )

    assert receipt.provider_id == DOUBAO_ID
    assert receipt.evidence_count == 1
    assert runtime.close_count == 1
    assert len(service.calls) == 1
    request, context, execution = service.calls[0]
    assert request.query == "What is retrieval augmented generation?"
    assert [(provider.id, provider.kind) for provider in request.providers] == [
        (DOUBAO_ID, "llm_search")
    ]
    assert request.strategy == "single"
    assert request.max_results_per_provider == 1
    assert context.request_id == "hfs-llm-provider-preflight"
    assert 0 < execution.remaining_seconds <= 7


@pytest.mark.asyncio
async def test_preflight_rate_limit_is_safe_single_attempt_without_model_fallback() -> None:
    service = _Service(
        error=ProviderError(
            ProviderErrorCode.RATE_LIMITED,
            provider_id=DEEPSEEK_ID,
            retry_after_seconds=1,
        )
    )
    runtime = _Runtime(service)

    with pytest.raises(preflight.PreflightFailure) as exc_info:
        await preflight.run_preflight(
            _Config((DEEPSEEK_ID,)),
            runtime_factory=lambda _config: runtime,
            timeout_seconds=5,
        )

    detail = str(exc_info.value)
    assert len(service.calls) == 1
    assert service.calls[0][0].providers[0].id == DEEPSEEK_ID
    assert DOUBAO_ID not in detail
    assert DEEPSEEK_ID in detail
    assert "rate_limited" in detail
    assert "retry_after=1" in detail
    assert runtime.close_count == 1


@pytest.mark.asyncio
async def test_preflight_sanitizes_provider_cancellation_and_closes_runtime() -> None:
    service = _CancelledService()
    runtime = _Runtime(service)

    with pytest.raises(preflight.PreflightFailure, match="provider_unavailable"):
        await preflight.run_preflight(
            _Config((DOUBAO_ID,)),
            runtime_factory=lambda _config: runtime,
        )

    assert len(service.calls) == 1
    assert runtime.close_count == 1


@pytest.mark.asyncio
async def test_preflight_rejects_zero_or_multiple_selected_providers_before_runtime() -> None:
    calls = 0

    def factory(_config):
        nonlocal calls
        calls += 1
        raise AssertionError("runtime must not be built")

    for selected in ((), (DEEPSEEK_ID, DOUBAO_ID)):
        with pytest.raises(preflight.PreflightFailure, match="exactly one"):
            await preflight.run_preflight(_Config(selected), runtime_factory=factory)
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ValueError("secret-canary"), RuntimeError("secret-canary")])
async def test_preflight_sanitizes_runtime_assembly_failures(error: Exception) -> None:
    def factory(_config):
        raise error

    with pytest.raises(preflight.PreflightFailure) as exc_info:
        await preflight.run_preflight(
            _Config((DOUBAO_ID,)),
            runtime_factory=factory,
        )

    assert "secret-canary" not in str(exc_info.value)
    assert "provider_unavailable" in str(exc_info.value)


def test_main_sanitizes_unexpected_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def unexpected_failure(*_args, **_kwargs):
        raise RuntimeError("cli-secret-canary")

    monkeypatch.setenv("SOUWEN_CONFIG_B64", "encoded")
    monkeypatch.setenv("UNIAPI_API_KEY", "api-key")
    monkeypatch.setattr(preflight, "load_preflight_config", lambda *_args: _Config((DOUBAO_ID,)))
    monkeypatch.setattr(preflight, "run_preflight", unexpected_failure)

    assert preflight.main([]) == 1
    captured = capsys.readouterr()
    assert "cli-secret-canary" not in captured.err
    assert "failed safely" in captured.err
