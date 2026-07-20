"""Shared secret redaction helper tests."""

from __future__ import annotations

from souwen.core.redaction import redact_secret_text


def test_redact_secret_text_scrubs_quoted_secret_key_values() -> None:
    """Free-form exception text often embeds JSON/dict-style secret fields."""
    text = (
        '{"api_key":"api-secret","safe":"ok"} '
        "{'client_secret': 'client-secret', 'trace': 'keep'} "
        'headers={"X-Api-Key":"header-secret"} '
        "token='token-secret'"
    )

    redacted = redact_secret_text(text)

    assert redacted is not None
    assert "api-secret" not in redacted
    assert "client-secret" not in redacted
    assert "header-secret" not in redacted
    assert "token-secret" not in redacted
    assert '"api_key":"***"' in redacted
    assert "'client_secret': '***'" in redacted
    assert '"X-Api-Key":"***"' in redacted
    assert "token:***" in redacted
    assert "token:***'" not in redacted
    assert '"safe":"ok"' in redacted
    assert "'trace': 'keep'" in redacted


def test_redact_secret_text_scrubs_authorization_scheme_credentials() -> None:
    """Authorization-style free text can carry a scheme plus a credential."""
    text = (
        "Authorization: Basic basic-secret-token "
        "Proxy-Authorization=Bearer proxy-secret-token "
        "callback https://example.test/cb?token=url-secret&safe=1"
    )

    redacted = redact_secret_text(text)

    assert redacted is not None
    assert "basic-secret-token" not in redacted
    assert "proxy-secret-token" not in redacted
    assert "url-secret" not in redacted
    assert "Authorization: ***" in redacted
    assert "Proxy-Authorization=***" in redacted
    assert "token=***" in redacted


def test_redact_secret_text_scrubs_quoted_scalar_secret_values() -> None:
    """Stringified JSON/Python dict payloads may carry numeric or boolean secrets."""
    text = (
        '{"api_key":123456,"token":true,"safe":"ok"} '
        "{'client_secret': 987654, 'session_id': None, 'trace': 'keep'}"
    )

    redacted = redact_secret_text(text)

    assert redacted is not None
    assert "123456" not in redacted
    assert "987654" not in redacted
    assert '"api_key":"***"' in redacted
    assert '"token":"***"' in redacted
    assert "'client_secret': '***'" in redacted
    assert "'session_id': '***'" in redacted
    assert '"safe":"ok"' in redacted
    assert "'trace': 'keep'" in redacted
