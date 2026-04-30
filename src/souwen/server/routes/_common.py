"""路由层共享工具 — 日志器与脱敏字段判断"""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException

logger = logging.getLogger("souwen.server")

_SECRET_KEYWORDS = {
    "key",
    "keys",
    "secret",
    "token",
    "password",
    "sessdata",
    "authorization",
    "auth",
}

# Pre-compiled splitter: underscore or hyphen
_FIELD_SPLITTER = re.compile(r"[_\-]")


def _is_secret_field(name: str) -> bool:
    """判断字段名是否包含敏感信息 — 用于脱敏配置输出

    按下划线/连字符分词后精确匹配关键字。同时完整匹配 Authorization 等常见 header 名。
    """
    parts = _FIELD_SPLITTER.split(name.lower())
    return any(part in _SECRET_KEYWORDS for part in parts)


def require_llm_enabled() -> None:
    """FastAPI dependency: 检查 LLM 功能是否启用，未启用返回 503。"""
    from souwen.config import get_config

    if not get_config().llm.enabled:
        raise HTTPException(status_code=503, detail="LLM feature is not enabled")
