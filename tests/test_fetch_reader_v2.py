"""Deterministic tests for the cached, paginated URL reader (SPEC 2.3/4.5)."""

from __future__ import annotations

import pytest

from souwen.modules.fetch.application.reader import (
    FetchReaderService,
    format_fetch_error,
    format_fetch_page,
)
from souwen.platform.provider_spi import (
    ContentMetadata,
    ErrorDetail,
    ExecutionContext,
    FetchBatch,
    FetchMeta,
    FetchRequest,
    FetchResult,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    RequestContext,
)


def _result(
    url: str,
    content: str,
    *,
    title: str | None = "Page title",
    status: str = "success",
    error: ErrorDetail | None = None,
    provider: str = "builtin-fetch",
) -> FetchResult:
    return FetchResult(
        target=url,
        final_url=url if status == "success" else None,
        status=status,
        title=title if status == "success" else None,
        content=content if status == "success" else None,
        content_metadata=(
            ContentMetadata(
                media_type="text/markdown",
                truncated=False,
                quality="low" if len(content.strip()) <= 63 else "high",
            )
            if status == "success"
            else None
        ),
        provenance=(
            Provenance(provider=provider, outcome="success" if status == "success" else "failed"),
        ),
        error=error,
    )


class _FakeModule:
    def __init__(self, result: FetchResult) -> None:
        self.result = result
        self.calls: list[str] = []

    async def fetch(self, request: FetchRequest, context, execution) -> FetchBatch:
        self.calls.append(str(request.targets[0]))
        return FetchBatch(
            items=(self.result,),
            meta=FetchMeta(partial=False),
            context=context,
        )


def _context() -> RequestContext:
    return RequestContext(request_id="reader-test")


def _execution() -> ExecutionContext:
    return ExecutionContext.with_timeout(10)


def _reader(module: _FakeModule, **kwargs) -> FetchReaderService:
    return FetchReaderService(module, **kwargs)


async def test_first_read_slices_from_zero_and_reports_continuation() -> None:
    body = "x" * 500
    module = _FakeModule(_result("https://example.com/a", body))
    reader = _reader(module)

    page = await reader.read(
        "https://example.com/a", max_chars=200, start=0, context=_context(), execution=_execution()
    )

    assert page.total_chars == 500
    assert page.content == "x" * 200
    assert page.start == 0
    assert page.next_start == 200
    assert page.title == "Page title"
    assert page.url == "https://example.com/a"
    assert page.egress == "direct"


async def test_continuation_uses_cache_without_refetch() -> None:
    module = _FakeModule(_result("https://example.com/a", "abcdefghij"))
    reader = _reader(module)

    first = await reader.read(
        "https://example.com/a", max_chars=4, start=0, context=_context(), execution=_execution()
    )
    second = await reader.read(
        "https://example.com/a", max_chars=4, start=4, context=_context(), execution=_execution()
    )
    tail = await reader.read(
        "https://example.com/a", max_chars=4, start=8, context=_context(), execution=_execution()
    )

    assert (first.content, first.next_start) == ("abcd", 4)
    assert (second.content, second.next_start) == ("efgh", 8)
    assert (tail.content, tail.next_start) == ("ij", None)
    assert module.calls == ["https://example.com/a"]


async def test_expired_entry_refetches() -> None:
    module = _FakeModule(_result("https://example.com/a", "content"))
    clock = {"now": 0.0}
    reader = FetchReaderService(module, cache_ttl_seconds=100.0, clock=lambda: clock["now"])

    await reader.read(
        "https://example.com/a", max_chars=5, start=0, context=_context(), execution=_execution()
    )
    clock["now"] = 100.0
    await reader.read(
        "https://example.com/a", max_chars=5, start=0, context=_context(), execution=_execution()
    )

    assert module.calls.count("https://example.com/a") == 2


async def test_start_beyond_end_returns_empty_tail() -> None:
    module = _FakeModule(_result("https://example.com/a", "short"))
    reader = _reader(module)

    page = await reader.read(
        "https://example.com/a", max_chars=10, start=999, context=_context(), execution=_execution()
    )

    assert page.content == ""
    assert page.start == 5  # clamped to total_chars
    assert page.next_start is None


async def test_failed_fetch_raises_typed_error_with_provider() -> None:
    failure = _result(
        "https://example.com/dead",
        "",
        status="failed",
        error=ErrorDetail(
            code="provider_timeout",
            message="Fetch provider timed out",
            retryable=True,
            request_id="reader-test",
            provider="builtin-fetch",
        ),
    )
    reader = _reader(_FakeModule(failure))

    with pytest.raises(ProviderError) as exc_info:
        await reader.read("https://example.com/dead", context=_context(), execution=_execution())

    assert exc_info.value.code is ProviderErrorCode.DEADLINE_EXCEEDED
    assert exc_info.value.provider_id == "builtin-fetch"
    assert "builtin-fetch" in format_fetch_error(exc_info.value)
    assert "To proceed:" in format_fetch_error(exc_info.value)


async def test_invalid_pagination_args_rejected_before_fetch() -> None:
    module = _FakeModule(_result("https://example.com/a", "content"))
    reader = _reader(module)

    with pytest.raises(ProviderError):
        await reader.read(
            "https://example.com/a", max_chars=0, context=_context(), execution=_execution()
        )
    with pytest.raises(ProviderError):
        await reader.read(
            "https://example.com/a", start=-1, context=_context(), execution=_execution()
        )
    assert module.calls == []


def test_format_page_header_and_tail() -> None:
    from souwen.modules.fetch.application.reader import FetchPage

    truncated = FetchPage(
        title="T",
        url="https://example.com/a",
        content="body",
        total_chars=100,
        start=0,
        next_start=4,
        egress="direct",
        sources=("builtin-fetch",),
    )
    complete = FetchPage(
        title=None,
        url="https://example.com/a",
        content="body",
        total_chars=4,
        start=0,
        next_start=None,
        egress="direct",
        sources=("builtin-fetch",),
    )

    truncated_text = format_fetch_page(truncated)
    complete_text = format_fetch_page(complete)

    assert truncated_text.splitlines()[0] == (
        "title: T | url: https://example.com/a | chars: 1-4 of 100 | egress: direct"
    )
    assert (
        truncated_text.splitlines()[-1] == "[truncated — call fetch again with start=4 to continue]"
    )
    assert "start=" not in complete_text
    assert "(untitled)" in complete_text


def test_cache_bounds_entries_fifo() -> None:
    class _MultiModule:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def fetch(self, request: FetchRequest, context, execution) -> FetchBatch:
            url = str(request.targets[0])
            self.calls.append(url)
            return FetchBatch(
                items=(_result(url, "c"),),
                meta=FetchMeta(partial=False),
                context=context,
            )

    module = _MultiModule()
    reader = FetchReaderService(module, cache_max_entries=2)
    urls = [f"https://example.com/{i}" for i in range(3)]

    async def scenario() -> None:
        for url in urls:
            await reader.read(url, context=_context(), execution=_execution())
        # 第一个 URL 已被逐出，重读会再次抓取并把 urls[1] 挤出去
        await reader.read(urls[0], context=_context(), execution=_execution())

    import asyncio

    asyncio.run(scenario())
    assert module.calls == urls + [urls[0]]
    assert set(reader._cache.keys()) == {urls[0], urls[2]}
