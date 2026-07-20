"""WARP runtime logging security regressions."""

from __future__ import annotations

import logging
import os
from urllib.parse import quote

import pytest

from souwen.server.warp import WarpManager


def _warp_log_messages(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(
        record.getMessage() for record in caplog.records if record.name == "souwen.warp"
    )


def test_apply_proxy_preserves_authenticated_env_without_logging_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    username = "local-user-secret"
    password = "local-password-token-secret"
    port = 11888
    expected_proxy = (
        f"socks5://{quote(username, safe='')}:{quote(password, safe='')}@127.0.0.1:{port}"
    )
    monkeypatch.setenv("SOUWEN_WARP_PROXY_USERNAME", username)
    monkeypatch.setenv("SOUWEN_WARP_PROXY_PASSWORD", password)

    with caplog.at_level(logging.INFO, logger="souwen.warp"):
        WarpManager._apply_proxy(port)

    messages = _warp_log_messages(caplog)
    assert os.environ["SOUWEN_PROXY"] == expected_proxy
    assert username not in messages
    assert password not in messages
    assert expected_proxy not in messages
    assert "proxy_type=socks5" in messages
    assert f"port={port}" in messages
    assert "auth_configured=True" in messages


def test_apply_external_proxy_preserves_env_without_logging_endpoint_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    proxy_url = (
        "socks5://external-user-secret:external-password-secret@proxy.example:1080"
        "?token=external-token-secret&region=hk#session=external-session-secret"
    )

    with caplog.at_level(logging.INFO, logger="souwen.warp"):
        WarpManager._apply_external_proxy(proxy_url)

    messages = _warp_log_messages(caplog)
    assert os.environ["SOUWEN_PROXY"] == proxy_url
    for sensitive_value in (
        proxy_url,
        "proxy.example",
        "external-user-secret",
        "external-password-secret",
        "external-token-secret",
        "external-session-secret",
    ):
        assert sensitive_value not in messages
    assert messages == "SOUWEN_PROXY 外部代理已配置并重载"
