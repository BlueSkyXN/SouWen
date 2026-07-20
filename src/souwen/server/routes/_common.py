"""路由层共享工具 — 日志器与脱敏字段判断"""

from __future__ import annotations

import logging

from fastapi import HTTPException

from souwen.core.redaction import (
    _is_secret_field as _is_secret_field,
    redact_secret_mapping as redact_secret_mapping,
    redact_secret_payload as redact_secret_payload,
    redact_secret_text as redact_secret_text,
    redact_secret_url as redact_secret_url,
    redact_secret_value as redact_secret_value,
)

logger = logging.getLogger("souwen.server")

__all__ = [
    "_is_secret_field",
    "logger",
    "normalize_optional_query_arg",
    "normalize_required_query_arg",
    "redact_secret_mapping",
    "redact_secret_payload",
    "redact_secret_text",
    "redact_secret_url",
    "redact_secret_value",
    "reject_redacted_placeholder",
    "require_llm_enabled",
]


def normalize_required_query_arg(value: str, name: str) -> str:
    """Strip a required string query/path argument and reject blank values."""
    stripped = value.strip()
    if not stripped:
        raise HTTPException(status_code=422, detail=f"{name} 不能是空字符串")
    return stripped


def normalize_optional_query_arg(value: str | None) -> str | None:
    """Strip an optional string query argument; blank values behave like omitted values."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def reject_redacted_placeholder(value: str | None, name: str) -> None:
    """Reject redacted display placeholders before they can overwrite real config."""
    if value and "***" in value:
        raise HTTPException(
            status_code=422,
            detail=f"{name} 是脱敏显示值，请重新输入完整值或保持该字段不变",
        )


def require_llm_enabled() -> None:
    """FastAPI dependency: 检查 LLM 功能是否可用。"""
    from souwen.config import get_config
    from souwen.editions import EditionError, ensure_edition_allowed

    cfg = get_config()
    try:
        ensure_edition_allowed("LLM", current=cfg.edition, required="pro")
    except EditionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not cfg.llm.enabled:
        raise HTTPException(status_code=503, detail="LLM feature is not enabled")
    if not cfg.llm.get_api_key():
        raise HTTPException(status_code=503, detail="LLM service not configured")
