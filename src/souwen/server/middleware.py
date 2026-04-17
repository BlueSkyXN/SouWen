"""SouWen ASGI 中间件 — 请求 ID 注入 + 响应计时 + 访问日志

文件用途：
    实现 Raw ASGI 中间件，为每个请求注入唯一 ID、记录响应时间和访问日志。
    支持跨协程传播 request_id 通过 contextvars。

核心设计：
    - Raw ASGI 而非 BaseHTTPMiddleware：异常发生时仍能正确写入响应头和日志
    - contextvars.ContextVar：线程安全地在异步调用栈中传播 request_id
    - X-Request-ID 和 X-Response-Time 响应头：便于客户端和 ELK 日志系统追踪

主要类/函数：
    get_request_id() -> str
        - 功能：获取当前请求的 ID（可在任何异步上下文调用）
        - 返回：request_id 字符串，或默认值 "-"

    RequestIDMiddleware(app)
        - 功能：Raw ASGI 中间件，处理 HTTP 请求和响应
        - 逻辑：
            1. 提取或生成 request_id（验证格式 [\w\-]{1,64}）
            2. 通过 contextvars 传播 ID
            3. 记录响应状态码和耗时
            4. 添加 X-Request-ID 和 X-Response-Time 响应头
            5. 记录访问日志（跳过 /health 和 /panel）

    RequestIDFilter(logging.Filter)
        - 功能：日志过滤器，自动注入 request_id 到所有日志记录
        - 使用：handler.addFilter(RequestIDFilter())

关键变量：
    request_id_var：ContextVar[str]，全局上下文变量，存储当前请求 ID
    _VALID_REQUEST_ID：正则表达式，验证 request_id 格式
    _SKIP_LOG_PATHS：无需记录访问日志的路径集合

模块依赖：
    - contextvars：上下文变量
    - logging：日志系统
"""

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
    """获取当前请求的关联 ID — 支持跨协程调用
    
    返回存储在 contextvars 中的 request_id。可在任何异步上下文（如背景任务、
    异步依赖、日志等）中调用，无需显式传递 request_id 参数。
    
    Returns:
        request_id 字符串，或默认值 "-" 当 context 未设置
    """
    return request_id_var.get()


class RequestIDMiddleware:
    """Raw ASGI 中间件 — 请求 ID 注入 + 响应计时 + 访问日志
    
    选择 Raw ASGI 而非 BaseHTTPMiddleware 的理由：
        - 异常发生时仍能正确写入响应头和日志（BaseHTTPMiddleware 可能丢失）
        - 兼容 contextvars 跨协程传播
        - 性能更好（直接操作 ASGI scope、receive、send）
    
    Parameters
    ----------
    app : ASGI app
        被包装的上游应用
    
    流程：
    1. 解析或生成 request_id
        - 从请求头 X-Request-ID 提取，若格式合法则使用
        - 否则生成随机 UUID（取前 12 个字符）
    2. 通过 contextvars 在异步上下文中传播 ID
    3. 记录请求的响应时间和状态码
    4. 添加响应头：X-Request-ID 和 X-Response-Time（秒，3 位小数）
    5. 记录访问日志（格式：METHOD PATH → STATUS (ELAPSED) [RID]）
    6. 清理 context 避免污染后续请求
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
    """日志过滤器 — 自动将 request_id 注入所有日志记录
    
    允许日志格式中包含 %(request_id)s 占位符，自动替换为当前请求的 ID。
    
    使用示例：
        handler = logging.StreamHandler()
        handler.addFilter(RequestIDFilter())
        formatter = logging.Formatter("%(asctime)s [%(request_id)s] %(message)s")
        handler.setFormatter(formatter)
    """

    def filter(self, record):
        record.request_id = request_id_var.get()
        return True
