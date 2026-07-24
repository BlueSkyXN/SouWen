"""Compatibility adapters around the canonical Common Runtime redaction primitives."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from souwen.common_runtime.security.redaction import (
    _is_secret_field as _is_secret_field,
    redact_secret_text as redact_secret_text,
    redact_secret_url as redact_secret_url,
    scrub_secret_text as scrub_secret_text,
)


def redact_secret_value(value: object, field_name: str | None = None) -> object:
    """Recursively redact values whose own field name indicates a secret."""
    if field_name and _is_secret_field(field_name) and value is not None:
        return "***"
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): redact_secret_value(item, str(key)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_secret_value(item) for item in value]
    return value


def redact_secret_payload(value: object, field_name: str | None = None) -> object:
    """Redact secret fields and scrub secret-looking text in arbitrary payloads."""
    redacted = redact_secret_value(value, field_name)
    if redacted == "***":
        return redacted
    if isinstance(redacted, Mapping):
        return {str(key): redact_secret_payload(item, str(key)) for key, item in redacted.items()}
    if isinstance(redacted, (list, tuple)):
        return [redact_secret_payload(item) for item in redacted]
    if isinstance(redacted, str):
        return redact_secret_text(redacted) or ""
    return redacted


def redact_llm_search_gateway_config_view(value: object) -> object:
    """Redact private LLM-search gateway endpoints in a configuration view.

    Gateway endpoints can expose private network topology even when they contain
    no credential-shaped URL component. This deliberately applies only to the
    ``llm_search_gateways`` config section; ordinary source ``base_url`` values
    retain their existing display contract.
    """
    redacted = redact_secret_payload(value)
    if not isinstance(redacted, Mapping):
        return redacted

    result: dict[str, object] = {}
    for gateway_id, gateway in redacted.items():
        if not isinstance(gateway, Mapping):
            result[str(gateway_id)] = gateway
            continue
        result[str(gateway_id)] = {
            str(field_name): "***" if field_name == "base_url" and field_value else field_value
            for field_name, field_value in gateway.items()
        }
    return result


def redact_secret_mapping(values: Mapping[str, object]) -> dict[str, object]:
    """Redact values whose field names look secret while preserving safe fields."""
    return {str(key): redact_secret_value(value, str(key)) for key, value in values.items()}
