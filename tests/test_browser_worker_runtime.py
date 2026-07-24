"""Fail-closed Browser Worker runtime settings."""

from __future__ import annotations

import pytest

from souwen.worker.browser_fetch.runtime import BrowserWorkerSettings
from souwen.worker.browser_fetch.protocol import BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST


def _valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOUWEN_BROWSER_WORKER_TOKEN", "r" * 48)
    monkeypatch.setenv("SOUWEN_SOURCE_SHA", "a" * 40)
    monkeypatch.setenv("SOUWEN_CONFIG_REVISION", "config-r1")


def test_runtime_defaults_to_exact_loopback_and_fixed_port(monkeypatch) -> None:
    _valid_env(monkeypatch)

    settings = BrowserWorkerSettings.from_env()

    assert settings.host == "127.0.0.1"
    assert settings.port == 49266
    assert settings.evidence.source_sha == "a" * 40
    assert settings.evidence.provider_inventory_digest == BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST


@pytest.mark.parametrize("host", ["0.0.0.0", "::1", "localhost", "127.0.0.2"])
def test_runtime_rejects_every_non_exact_bind_host(monkeypatch, host: str) -> None:
    _valid_env(monkeypatch)
    monkeypatch.setenv("SOUWEN_BROWSER_WORKER_HOST", host)

    with pytest.raises(ValueError):
        BrowserWorkerSettings.from_env()


def test_runtime_requires_internal_token_and_provenance(monkeypatch) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    monkeypatch.delenv("SOUWEN_SOURCE_SHA", raising=False)
    monkeypatch.delenv("SOUWEN_CONFIG_REVISION", raising=False)

    with pytest.raises(ValueError):
        BrowserWorkerSettings.from_env()
