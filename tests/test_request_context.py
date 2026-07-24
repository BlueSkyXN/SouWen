"""Common Runtime request-correlation context parity tests."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from souwen import logging_config
from souwen.common_runtime.observability import (
    RequestIDFilter,
    get_request_id,
    request_id_var,
)
from souwen.common_runtime.observability import request_context as canonical_context
from souwen.server import middleware as legacy_middleware


def test_legacy_request_context_path_reexports_canonical_interface() -> None:
    assert legacy_middleware.RequestIDFilter is RequestIDFilter
    assert legacy_middleware.get_request_id is get_request_id
    assert legacy_middleware.request_id_var is request_id_var
    assert logging_config.RequestIDFilter is RequestIDFilter


def test_request_context_defaults_and_resets() -> None:
    assert get_request_id() == "-"

    token = request_id_var.set("request-123")
    try:
        assert get_request_id() == "request-123"
    finally:
        request_id_var.reset(token)

    assert get_request_id() == "-"


def test_request_id_filter_injects_current_context() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", (), None)
    token = request_id_var.set("filter-request")
    try:
        assert RequestIDFilter().filter(record) is True
    finally:
        request_id_var.reset(token)

    assert record.request_id == "filter-request"


@pytest.mark.asyncio
async def test_request_context_is_isolated_across_tasks() -> None:
    async def observe(request_id: str) -> tuple[str, str]:
        token = request_id_var.set(request_id)
        try:
            await asyncio.sleep(0)
            current = get_request_id()
        finally:
            request_id_var.reset(token)
        return current, get_request_id()

    assert await asyncio.gather(observe("request-a"), observe("request-b")) == [
        ("request-a", "-"),
        ("request-b", "-"),
    ]
    assert get_request_id() == "-"


def test_canonical_request_context_has_only_stdlib_dependencies() -> None:
    source = Path(canonical_context.__file__).read_text(encoding="utf-8")

    assert "from souwen" not in source
    assert "import souwen" not in source
