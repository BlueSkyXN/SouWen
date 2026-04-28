"""路由层共享工具 — 日志器与脱敏字段判断"""

from __future__ import annotations

import logging

from fastapi import HTTPException

logger = logging.getLogger("souwen.server")

_SECRET_KEYWORDS = {"key", "keys", "secret", "token", "password", "sessdata"}


def _is_secret_field(name: str) -> bool:
    """判断字段名是否包含敏感信息 — 用于脱敏配置输出

    按下划线分词后精确匹配关键字，避免 max_tokens / max_input_tokens 等
    非敏感字段被误判为密钥字段。
    """
    return any(part in _SECRET_KEYWORDS for part in name.lower().split("_"))


def require_llm_enabled() -> None:
    """FastAPI dependency: 检查 LLM 功能是否启用，未启用返回 503。"""
    from souwen.config import get_config

    if not get_config().llm.enabled:
        raise HTTPException(status_code=503, detail="LLM feature is not enabled")
