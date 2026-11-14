"""SouWen 集中日志配置"""

from __future__ import annotations

import json as _json
import logging
import os
import sys
from datetime import datetime, timezone

from souwen.common_runtime.observability import RequestIDFilter
from souwen.common_runtime.security import redact_secret_text

_CONFIGURED = False


def _scrub(text: str | None) -> str | None:
    """脱敏日志文本：Authorization/Bearer、常见敏感键的值替换为 ***

    处理两种常见敏感数据格式：
    1. Bearer token 模式：Authorization: Bearer xxx → Authorization: Bearer ***
    2. Key-value 模式：api_key=xxx / password: xxx → api_key=*** / password: ***

    Args:
        text: 原始日志文本

    Returns:
        脱敏后的文本
    """
    return redact_secret_text(text)


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
