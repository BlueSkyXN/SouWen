"""Common Runtime generic secret-redaction parity and dependency tests."""

from __future__ import annotations

import ast
from pathlib import Path

from pydantic import BaseModel
import pytest

from souwen import logging_config, plugin_manager
from souwen.common_runtime.security import (
    redact_secret_text,
    redact_secret_url,
    scrub_secret_text,
)
from souwen.common_runtime.security import redaction as canonical_redaction
from souwen.core import redaction as legacy_redaction


def test_core_redaction_reexports_canonical_text_and_url_primitives() -> None:
    assert legacy_redaction._is_secret_field is canonical_redaction._is_secret_field
    assert legacy_redaction.redact_secret_text is redact_secret_text
    assert legacy_redaction.redact_secret_url is redact_secret_url
    assert legacy_redaction.scrub_secret_text is scrub_secret_text


def test_logging_and_plugin_manager_use_canonical_redaction() -> None:
    assert logging_config.redact_secret_text is redact_secret_text
    assert plugin_manager.redact_secret_text is redact_secret_text


def test_canonical_redaction_has_only_stdlib_dependencies() -> None:
    path = Path(canonical_redaction.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported_roots = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        (node.module or "").split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )

    assert imported_roots == {"__future__", "re", "urllib"}


def test_text_redaction_preserves_url_punctuation_and_safe_fields() -> None:
    secret_text = (
        "request failed "
        "(https://user:password@example.test/cb?apiKey=query-secret&safe=1#token=fragment). "
        "Authorization: Bearer bearer-secret-token "
        '{"client_secret":"json-secret","trace":"keep"}'
    )

    redacted = redact_secret_text(secret_text)

    assert redacted is not None
    for secret in (
        "password",
        "query-secret",
        "fragment",
        "bearer-secret-token",
        "json-secret",
    ):
        assert secret not in redacted
    assert "(https://***@example.test/cb?apiKey=***&safe=1#token=***)." in redacted
    assert "Authorization: ***" in redacted
    assert '"client_secret":"***"' in redacted
    assert '"trace":"keep"' in redacted


def test_url_redaction_preserves_non_secret_query_and_fragment_fields() -> None:
    assert redact_secret_url(
        "https://user:pass@example.test/path?api%5Fkey=secret;page=2#token=fragment&view=full"
    ) == ("https://***@example.test/path?api%5Fkey=***;page=2#token=***&view=full")
    assert redact_secret_url(None) == ""
    assert scrub_secret_text(None) is None
    assert scrub_secret_text("") == ""


def test_canonical_url_redaction_propagates_parser_failure_without_returning_raw_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_closed(_url: str):
        raise ValueError("parser unavailable")

    monkeypatch.setattr(canonical_redaction, "urlsplit", fail_closed)

    with pytest.raises(ValueError, match="parser unavailable"):
        redact_secret_url("https://user:do-not-return@example.test/?token=do-not-return")


def test_pydantic_and_llm_gateway_policies_remain_legacy_adapters() -> None:
    class SecretModel(BaseModel):
        api_key: str
        safe: str

    assert not hasattr(canonical_redaction, "redact_secret_payload")
    assert not hasattr(canonical_redaction, "redact_llm_search_gateway_config_view")
    assert legacy_redaction.redact_secret_payload(
        SecretModel(api_key="model-secret", safe="keep")
    ) == {"api_key": "***", "safe": "keep"}
    assert legacy_redaction.redact_llm_search_gateway_config_view(
        {
            "gateway": {
                "base_url": "https://private-gateway.example/v1",
                "api_key": "gateway-secret",
                "model": "example-model",
            }
        }
    ) == {
        "gateway": {
            "base_url": "***",
            "api_key": "***",
            "model": "example-model",
        }
    }
