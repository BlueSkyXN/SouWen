"""Deterministic Provider SPI port and execution-context conformance tests."""

from __future__ import annotations

import ast
import asyncio
import time
from pathlib import Path

import pytest

from souwen.modules.fetch.api import FetchModule
from souwen.modules.llm_search.api import LLMSearchModule
from souwen.modules.search.api import SearchModule
from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchProvider,
    LLMSearchProvider,
    ProviderError,
    ProviderErrorCode,
    SearchProvider,
)


class _SearchAdapter:
    capability = "search"

    async def search(self, request, context, execution):  # noqa: ANN001
        raise NotImplementedError

    async def probe(self, execution):  # noqa: ANN001
        raise NotImplementedError

    async def close(self) -> None:
        return None


class _LLMSearchAdapter:
    capability = "llm_search"

    async def search(self, request, context, execution):  # noqa: ANN001
        raise NotImplementedError

    async def probe(self, execution):  # noqa: ANN001
        raise NotImplementedError

    async def close(self) -> None:
        return None


class _FetchAdapter:
    capability = "fetch"

    async def fetch(self, request, context, execution):  # noqa: ANN001
        raise NotImplementedError

    async def probe(self, execution):  # noqa: ANN001
        raise NotImplementedError

    async def close(self) -> None:
        return None


def test_each_adapter_protocol_has_one_capability() -> None:
    assert isinstance(_SearchAdapter(), SearchProvider)
    assert isinstance(_LLMSearchAdapter(), LLMSearchProvider)
    assert isinstance(_FetchAdapter(), FetchProvider)
    assert SearchProvider.__dict__["__annotations__"]["capability"] == "Literal['search']"
    assert LLMSearchProvider.__dict__["__annotations__"]["capability"] == "Literal['llm_search']"
    assert FetchProvider.__dict__["__annotations__"]["capability"] == "Literal['fetch']"


def test_execution_context_uses_absolute_monotonic_deadline_and_cancellation() -> None:
    cancel_event = asyncio.Event()
    context = ExecutionContext.with_timeout(30, cancel_event=cancel_event)

    assert context.deadline_monotonic > time.monotonic()
    assert 0 < context.remaining_seconds <= 30
    cancel_event.set()
    assert context.cancelled is True
    with pytest.raises(ProviderError) as exc_info:
        context.raise_if_cancelled_or_expired()
    assert exc_info.value.code is ProviderErrorCode.CANCELLED


def test_execution_context_bounds_distant_deadlines_and_rejects_invalid_timeouts() -> None:
    distant = ExecutionContext(deadline_monotonic=time.monotonic() + 1_000)
    assert distant.remaining_seconds == 120
    assert ExecutionContext(deadline_monotonic=time.monotonic() - 1).expired is True
    with pytest.raises(ValueError):
        ExecutionContext.with_timeout(121)
    with pytest.raises(ProviderError) as exc_info:
        ExecutionContext(deadline_monotonic=time.monotonic() - 1).raise_if_cancelled_or_expired()
    assert exc_info.value.code is ProviderErrorCode.DEADLINE_EXCEEDED


def test_provider_errors_expose_only_safe_taxonomy() -> None:
    error = ProviderError(
        ProviderErrorCode.RATE_LIMITED,
        provider_id="fixture-provider",
        retry_after_seconds=2,
    )

    assert error.retryable is True
    assert str(error) == "Provider rate limit was reached"
    assert error.provider_id == "fixture-provider"


def test_module_public_api_imports_only_provider_spi() -> None:
    assert SearchModule.__module__ == "souwen.modules.search.api"
    assert LLMSearchModule.__module__ == "souwen.modules.llm_search.api"
    assert FetchModule.__module__ == "souwen.modules.fetch.api"

    root = Path(__file__).resolve().parents[1]
    for path in (
        root / "src/souwen/modules/search/api/__init__.py",
        root / "src/souwen/modules/llm_search/api/__init__.py",
        root / "src/souwen/modules/fetch/api/__init__.py",
    ):
        imports = [
            node.module
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        assert "souwen.platform.provider_spi" in imports
        assert not any(module.startswith("souwen.providers") for module in imports)
