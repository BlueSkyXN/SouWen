"""路由层共享工具 — 日志器与脱敏字段判断"""

from __future__ import annotations

import logging

logger = logging.getLogger("souwen.server")

_SECRET_KEYWORDS = {"key", "secret", "token", "password", "sessdata"}


def _is_secret_field(name: str) -> bool:
    """判断字段名是否包含敏感信息 — 用于脱敏配置输出

    检查字段名中是否包含 key、secret、token、password 关键词。
    """
    return any(kw in name for kw in _SECRET_KEYWORDS)
