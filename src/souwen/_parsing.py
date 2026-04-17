"""通用解析工具

文件用途：
    提供跨数据源复用的宽松解析器，优先容错设计：
    接受 None、空串、非法格式时返回 None 而非抛异常，
    记录 debug 日志但不警告，避免填充日志。

函数清单：
    safe_parse_date(value) -> date | None
        - 功能：宽松解析日期字符串/对象，支持多种格式
        - 入参：value 任意输入（str|date|datetime|None 等）
        - 出参：解析成功返回 date；非法或空值返回 None
        - 支持格式：None/空字符串 → None; date/datetime 对象; 
                   ISO 8601 格式（YYYY、YYYY-MM、YYYY-MM-DD、带时区部分）
        - 关键：失败不抛异常，debug 记录便于排查

模块依赖：
    - datetime: date/datetime 类型
    - logging: debug 级别日志
"""

from __future__ import annotations

import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)


def safe_parse_date(value: date | str | datetime | None) -> date | None:
    """宽松解析日期字符串/对象

    支持多种格式且容错：
    - ``None`` / 空字符串 → 返回 None
    - ``date`` / ``datetime`` 对象 → 返回 date
    - ISO 8601 字符串：``YYYY``、``YYYY-MM``、``YYYY-MM-DD``、
      带时区/时间部分也可（会自动截断）
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
