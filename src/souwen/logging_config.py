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
import re
import sys
from datetime import datetime, timezone

from souwen.server.middleware import RequestIDFilter

_CONFIGURED = False


# ==============================================================================
# 敏感数据脱敏
# ==============================================================================
# 避免将 token / Authorization / API key 等敏感信息写入日志文件

_SENSITIVE_KEY = re.compile(
    r"(authorization|auth[_-]?token|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|secret|password|passwd|pwd|x[_-]?api[_-]?key|"
    r"souwen[_-]?token|token|bearer)",
    re.IGNORECASE,
)

# 1. Authorization 头 / "Bearer xxx" 模式
_RE_BEARER = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9\-_.=+/]{6,})")

# 2. key=value / key: value / "key": "value" 中敏感键对应的值
_RE_KV = re.compile(
    r"(?i)(" + _SENSITIVE_KEY.pattern + r")\s*[:=]\s*[\"']?([^\s,\"'}\]]+)"
)


def _mask_token(value: str) -> str:
    """将 token 字符串替换为固定占位符 ***"""
    if not value:
        return value
    return "***"


def _scrub(text: str) -> str:
    """脱敏日志文本：Authorization/Bearer、常见敏感键的值替换为 ***"""
    if not text or not isinstance(text, str):
        return text
    text = _RE_BEARER.sub(lambda m: m.group(0).replace(m.group(1), _mask_token(m.group(1))), text)
    text = _RE_KV.sub(lambda m: f"{m.group(1)}:***", text)
    return text


class SensitiveDataFilter(logging.Filter):
    """logging.Filter：对 record.msg 与 args 做敏感数据脱敏。

    覆盖面：
    - Authorization: Bearer xxx
    - api_key=xxx / token: xxx / "password": "xxx" 等常见形态
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = _scrub(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: _scrub(v) if isinstance(v, str) else v for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        _scrub(a) if isinstance(a, str) else a for a in record.args
                    )
        except Exception:
            # 日志过滤器不可抛错，失败时放行原记录
            pass
        return True


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
    handler.addFilter(SensitiveDataFilter())

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
