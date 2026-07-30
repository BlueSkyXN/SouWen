"""Rate-limit proxy parsing security regressions."""

from __future__ import annotations

import logging

import pytest

from souwen.server.limiter import _parse_trusted_networks


def test_invalid_trusted_proxy_is_rejected_without_logging_its_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_value = (
        "https://internal-user:internal-password@proxy.example"
        "?token=internal-token#session=internal-session"
    )

    with caplog.at_level(logging.WARNING, logger="souwen.server.limiter"):
        networks = _parse_trusted_networks([sensitive_value])

    messages = "\n".join(
        record.getMessage() for record in caplog.records if record.name == "souwen.server.limiter"
    )
    assert networks == []
    for secret_part in (
        sensitive_value,
        "internal-user",
        "internal-password",
        "proxy.example",
        "internal-token",
        "internal-session",
    ):
        assert secret_part not in messages
    assert messages == "trusted_proxies 中存在不是合法 IP/CIDR 的条目，已忽略"
