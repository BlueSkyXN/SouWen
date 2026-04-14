"""SouWen ASGI 中间件 — 请求日志 + Request ID + 响应计时"""

from __future__ import annotations

import logging
import re
import time
from contextvars import ContextVar
from uuid import uuid4

# 当前请求 ID — 任何模块均可通过 get_request_id() 读取
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

logger = logging.getLogger("souwen.server")

_VALID_REQUEST_ID = re.compile(r"^[\w\-]{1,64}$")

# 不记录访问日志的路径（健康检查 / 面板静态资源）
_SKIP_LOG_PATHS = frozenset({"/health", "/panel"})


def get_request_id() -> str:
    """获取当前请求的关联 ID（可在任何异步上下文中调用）"""
    return request_id_var.get()


class RequestIDMiddleware:
    """Raw ASGI 中间件：注入 X-Request-ID + 响应计时 + 访问日志。

    选择 raw ASGI 而非 BaseHTTPMiddleware 的理由:
    - 异常发生时仍能正确写入响应头和日志
    - 兼容 contextvars 跨协程传播
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # --- 提取或生成 Request ID ---
        headers = dict(scope.get("headers", []))
        raw_id = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        if raw_id and _VALID_REQUEST_ID.match(raw_id):
            rid = raw_id
        else:
            rid = uuid4().hex[:12]

        token = request_id_var.set(rid)
        start = time.monotonic()
        status_code = 500  # default in case send never called

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                extra_headers = [
                    (b"x-request-id", rid.encode()),
                    (b"x-response-time", f"{time.monotonic() - start:.3f}s".encode()),
                ]
                message = {
                    **message,
                    "headers": list(message.get("headers", [])) + extra_headers,
                }
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("unhandled error [%s]", rid)
            raise
        finally:
            elapsed = time.monotonic() - start
            path = scope.get("path", "/")
            if path not in _SKIP_LOG_PATHS:
                method = scope.get("method", "?")
                logger.info(
                    "%s %s → %d (%.3fs) [%s]",
                    method,
                    path,
                    status_code,
                    elapsed,
                    rid,
                )
            request_id_var.reset(token)


class RequestIDFilter(logging.Filter):
    """日志过滤器：自动将 request_id 注入所有日志记录。

    使用方法:
        handler.addFilter(RequestIDFilter())
        formatter = logging.Formatter("%(asctime)s %(request_id)s %(message)s")
    """

    def filter(self, record):
        record.request_id = request_id_var.get()
        return True
