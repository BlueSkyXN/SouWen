"""SouWen 集中日志配置

Usage:
    from souwen.logging_config import setup_logging
    setup_logging()                # 默认 INFO + 文本格式
    setup_logging(level="DEBUG")   # 调试模式
    setup_logging(json_format=True)# JSON 结构化（生产/Docker）

环境变量:
    SOUWEN_LOG_LEVEL  — DEBUG | INFO | WARNING | ERROR (默认 INFO)
    SOUWEN_LOG_FORMAT — text | json (默认 text)
"""

from __future__ import annotations

import json as _json
import logging
import os
import sys
from datetime import datetime, timezone

from souwen.server.middleware import RequestIDFilter

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """JSON 行格式化器（每行一个 JSON 对象，方便日志采集）"""

    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info and record.exc_info[0] is not None:
            obj["exception"] = self.formatException(record.exc_info)
        return _json.dumps(obj, ensure_ascii=False)


def setup_logging(
    level: str | None = None,
    json_format: bool | None = None,
) -> None:
    """配置 souwen 根日志器（幂等，多次调用安全）。

    Args:
        level: 日志级别，默认从 SOUWEN_LOG_LEVEL 环境变量读取，缺省 INFO
        json_format: 是否使用 JSON 格式，默认从 SOUWEN_LOG_FORMAT 读取
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    level = level or os.environ.get("SOUWEN_LOG_LEVEL", "INFO")
    if json_format is None:
        json_format = os.environ.get("SOUWEN_LOG_FORMAT", "text").lower() == "json"

    # 配置 souwen 命名空间
    souwen_logger = logging.getLogger("souwen")
    souwen_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(RequestIDFilter())

    if json_format:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s — %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    souwen_logger.addHandler(handler)
    souwen_logger.propagate = False

    # 降低第三方库日志噪音
    for noisy in ("httpx", "httpcore", "urllib3", "hpack", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
