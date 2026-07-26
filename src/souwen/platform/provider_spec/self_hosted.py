"""Validation helpers for deployment-owned self-hosted Provider endpoints."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit


def validate_self_hosted_base_url(value: Any) -> str:
    """Normalize one admin-configured HTTP(S) origin without applying public-target SSRF rules."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("self-hosted base_url is required")
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or any(character.isspace() for character in parsed.hostname)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid self-hosted base_url")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid self-hosted base_url") from exc
    host = parsed.hostname.lower()
    rendered_host = f"[{host}]" if ":" in host else host
    netloc = rendered_host if port is None else f"{rendered_host}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


__all__ = ["validate_self_hosted_base_url"]
