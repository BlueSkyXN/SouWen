"""SouWen 集中日志配置

文件用途：
    统一配置 souwen 命名空间的日志输出（文本或 JSON），
    包括敏感数据脱敏、请求 ID 追踪、日志级别管理等。

配置来源：
    1. 函数参数（优先级最高）
    2. 环境变量（SOUWEN_LOG_LEVEL、SOUWEN_LOG_FORMAT）
    3. 默认值（INFO 级别、文本格式）

类/函数清单：
    SensitiveDataFilter（logging.Filter）
        - 功能：日志敏感数据脱敏过滤器
        - 方法：filter(record) → bool — 对日志记录的消息和参数做脱敏
        - 脱敏对象：Authorization/Bearer token、api_key、password 等敏感字段值

    _JsonFormatter（logging.Formatter）
        - 功能：JSON 行格式化器（每行一个 JSON 对象）
        - 输出格式：{"ts": ISO8601, "level": "INFO", "logger": "souwen.xxx",
                   "msg": "...", "request_id": "...", "exception": "..."}
        - 用途：适合日志聚合系统（ELK、Datadog 等）

    setup_logging(level, json_format) → None
        - 功能：配置 souwen 根日志器（幂等，多次调用安全）
        - 入参：level (str) 日志级别, json_format (bool) 是否 JSON 格式
        - 默认值：从 SOUWEN_LOG_LEVEL / SOUWEN_LOG_FORMAT 环境变量读取
        - 副作用：添加 Handler、Filter、Formatter 到 souwen logger；降低第三方库日志级别
        - 说明：第三方库（httpx、urllib3 等）日志降低到 WARNING 避免噪音

环境变量：
    SOUWEN_LOG_LEVEL: DEBUG | INFO | WARNING | ERROR（默认 INFO）
    SOUWEN_LOG_FORMAT: text | json（默认 text）

脱敏规则：
    - Bearer token 模式：Authorization: Bearer xxx → Authorization: Bearer ***
    - Key-value 模式：api_key=xxx / password: xxx → api_key=*** / password:***
    - 匹配的关键字：authorization、token、api_key、secret、password 等

模块依赖：
    - logging: 标准日志框架
    - json: JSON 格式化
    - datetime/timezone: 时间戳
    - re: 正则匹配敏感数据
    - souwen.server.middleware.RequestIDFilter: 请求 ID 追踪
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
_RE_KV = re.compile(r"(?i)(" + _SENSITIVE_KEY.pattern + r")\s*[:=]\s*[\"']?([^\s,\"'}\]]+)")


def _mask_token(value: str) -> str:
    """将 token 字符串替换为固定占位符

    Args:
        value: 要脱敏的 token 值

    Returns:
        空值返回原值，非空返回 '***'
    """
    if not value:
        return value
    return "***"


def _scrub(text: str) -> str:
    """脱敏日志文本：Authorization/Bearer、常见敏感键的值替换为 ***

    处理两种常见敏感数据格式：
    1. Bearer token 模式：Authorization: Bearer xxx → Authorization: Bearer ***
    2. Key-value 模式：api_key=xxx / password: xxx → api_key=*** / password: ***

    Args:
        text: 原始日志文本

    Returns:
        脱敏后的文本
    """
    if not text or not isinstance(text, str):
        return text
    text = _RE_BEARER.sub(lambda m: m.group(0).replace(m.group(1), _mask_token(m.group(1))), text)
    text = _RE_KV.sub(lambda m: f"{m.group(1)}:***", text)
    return text


class SensitiveDataFilter(logging.Filter):
    """logging.Filter：对 record.msg 与 args 做敏感数据脱敏

    覆盖面：
    - Authorization: Bearer xxx
    - api_key=xxx / token: xxx / "password": "xxx" 等常见形态

    方法：
        filter(record: logging.LogRecord) → bool
            - 脱敏 record.msg 字符串
            - 脱敏 record.args 中的字符串值
            - 异常不抛出，失败时放行原记录（日志过滤器不可中断）
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """对日志记录做敏感数据脱敏

        Args:
            record: 日志记录对象

        Returns:
            总是返回 True（允许记录）

        说明：
            - 不修改 record 对象本身，而是修改消息和参数
            - 异常时仍返回 True（不中断日志流程）
        """
        try:
            if isinstance(record.msg, str):
                record.msg = _scrub(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: _scrub(v) if isinstance(v, str) else v for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(_scrub(a) if isinstance(a, str) else a for a in record.args)
        except Exception:
            # 日志过滤器不可抛错，失败时放行原记录
            pass
        return True


class _JsonFormatter(logging.Formatter):
    """JSON 行格式化器（每行一个 JSON 对象，方便日志采集）

    输出格式：单行 JSON，包含：
    - ts: 时间戳（ISO 8601，UTC）
    - level: 日志级别（DEBUG、INFO 等）
    - logger: 日志器名称
    - msg: 日志消息
    - request_id: 请求 ID（来自 RequestIDFilter）
    - exception: 异常堆栈（若 exc_info 存在）

    用途：
        - 结构化日志采集（ELK、Datadog、Splunk 等）
        - 机器可读的日志分析
    """

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为 JSON 行

        Args:
            record: 日志记录对象

        Returns:
            单行 JSON 字符串
        """
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
    """配置 souwen 根日志器（幂等，多次调用安全）

    配置日志输出包括：
    - souwen 命名空间根 logger：指定级别 + Handler
    - 敏感数据脱敏 + 请求 ID 追踪
    - 可选文本或 JSON 格式
    - 第三方库日志降级处理

    Args:
        level: 日志级别（DEBUG、INFO、WARNING、ERROR）；
               不指定则从 SOUWEN_LOG_LEVEL 环境变量读取，缺省 INFO
        json_format: 是否使用 JSON 格式；
                     不指定则从 SOUWEN_LOG_FORMAT 环境变量读取，缺省 False

    说明：
        - 幂等性：_CONFIGURED 标志保证多次调用后仅配置一次
        - 第三方库名单：httpx、httpcore、urllib3、hpack、charset_normalizer
          都被降低到 WARNING 级别以减少日志噪音
        - JSON 格式适合 Docker/容器部署和日志聚合系统
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
