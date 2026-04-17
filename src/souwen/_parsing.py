"""通用解析工具

提供跨数据源复用的宽松解析器，优先考虑容错：
- 接受 ``None``、空串、非法格式时返回 ``None`` 而非抛异常
- 记录 debug 日志方便排查，但不 warning 以免刷屏
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)


def safe_parse_date(value: Any) -> date | None:
    """宽松解析日期字符串/对象。

    支持：
    - ``None`` / 空字符串 → 返回 None
    - ``date`` / ``datetime`` 对象 → 返回 date
    - ISO 8601 字符串：``YYYY``、``YYYY-MM``、``YYYY-MM-DD``、带时区/时间部分
    - 任何非法格式 → 返回 None（debug 日志）

    Args:
        value: 任意输入。

    Returns:
        解析成功返回 ``date``；否则 ``None``。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        logger.debug("safe_parse_date: 不支持的类型 %s", type(value).__name__)
        return None

    text = value.strip()
    if not text:
        return None

    # 截断时间部分（ISO 8601 带 T 分隔）
    if "T" in text:
        text = text.split("T", 1)[0]

    # 完整 YYYY-MM-DD
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass

    # YYYY-MM（补 01 日）
    if len(text) == 7 and text[4] == "-":
        try:
            return date.fromisoformat(f"{text}-01")
        except ValueError:
            pass

    # YYYY（补 01-01）
    if len(text) == 4 and text.isdigit():
        try:
            return date(int(text), 1, 1)
        except ValueError:
            pass

    logger.debug("safe_parse_date: 无法解析 %r", value)
    return None
