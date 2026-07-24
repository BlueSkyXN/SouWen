"""Request correlation context shared by protocol and logging adapters."""

from __future__ import annotations

import logging
from contextvars import ContextVar


request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the current correlation ID or ``"-"`` outside a request context."""
    return request_id_var.get()


class RequestIDFilter(logging.Filter):
    """Inject the current correlation ID into a log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


__all__ = ["RequestIDFilter", "get_request_id", "request_id_var"]
