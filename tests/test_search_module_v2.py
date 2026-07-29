"""Deterministic Search Module v2 orchestration conformance tests."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import pytest

from souwen.modules.search.api import SearchModuleService
from souwen.modules.search.application import (
    OrderedSearchProviderSelector,
    SearchProviderSelection,
)
from souwen.platform.provider_spi import (
    ExecutionContext,
    PageInfo,
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    ProviderRef,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchIdentifier,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)


def _context() -> RequestContext:
    return RequestContext(request_id="search-module-test")


def _execution() -> ExecutionContext:
    return ExecutionContext.with_timeout(30)


def _provider(provider_id: str) -> ProviderRef:
    return ProviderRef(id=provider_id, kind="search")


def _selection(provider_id: str, *, priority: int = 10) -> SearchProviderSelection:
    return SearchProviderSelection(
        provider=_provider(provider_id),
        adapter_id=f"{provider_id}-adapter",
        yaml_priority=priority,
    )


def _item(
    item_id: str,
    *,
    title: str | None = None,
    rank: int = 1,
    provider: str = "openalex",
    url: str | None = None,
    doi: str | None = None,
    year: int | None = None,
) -> SearchItem:
    identifiers = (SearchIdentifier(scheme="doi", value=doi),) if doi is not None else ()
    return SearchItem(
        id=item_id,
        title=title or item_id,
        rank=rank,
        url=url,
        provenance=(Provenance(provider=provider, outcome="success"),),
        attributes=SearchAttributes(identifiers=identifiers, year=year),
    )


def _page(context: RequestContext, *items: SearchItem) -> SearchPage:
    return SearchPage(
        items=items,
        page=PageInfo(limit=10),
        meta=SearchMeta(),
        context=context,
    )


@dataclass
class _Selector:
    default: tuple[SearchProviderSelection, ...]
    explicit: tuple[SearchProviderSelection, ...] = ()
    default_calls: int = 0
    explicit_calls: int = 0

    def select_default(self, request: SearchRequest) -> tuple[SearchProviderSelection, ...]:
        self.default_calls += 1
        return self.default

    def select_explicit(
        self, providers: tuple[ProviderRef, ...]
    ) -> tuple[SearchProviderSelection, ...]:
        self.explicit_calls += 1
        return self.explicit


@dataclass
class _Manager:
    outcomes: dict[str, SearchPage | BaseException]
    calls: list[str] = field(default_factory=list)

    async def execute(self, adapter_id, request, context, execution):  # noqa: ANN001
        self.calls.append(adapter_id)
        outcome = self.outcomes[adapter_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_absent_providers_selects_exactly_one_yaml_primary() -> None:
    context = _context()
    primary = _selection("openalex", priority=3)
    selector = _Selector(default=(primary,))
    manager = _Manager({primary.adapter_id: _page(context, _item("openalex:1"))})
    service = SearchModuleService(manager, selector)

    result = await service.search(
        SearchRequest(query="query", domains=("paper",)), context, _execution()
    )

    assert selector.default_calls == 1
    assert selector.explicit_calls == 0
    assert manager.calls == [primary.adapter_id]
    assert result.meta == SearchMeta(requested=("openalex",), succeeded=("openalex",))


def test_ordered_selector_projects_yaml_priority_and_explicit_identity() -> None:
    lower = _selection("lower", priority=20)
    primary = _selection("primary", priority=1)
    selector = OrderedSearchProviderSelector({"paper": (lower, primary)})

    assert selector.select_default(SearchRequest(query="query", domains=("paper",))) == (primary,)
    assert selector.select_explicit((_provider("lower"), _provider("primary"))) == (
        lower,
        primary,
    )
    with pytest.raises(ProviderError) as multi_domain:
        selector.select_default(SearchRequest(query="query", domains=("paper", "web")))
    assert multi_domain.value.code is ProviderErrorCode.INVALID_REQUEST


@pytest.mark.asyncio
async def test_explicit_single_provider_never_fans_out() -> None:
    context = _context()
    selected = _selection("openalex")
    selector = _Selector(default=(), explicit=(selected,))
    manager = _Manager({selected.adapter_id: _page(context, _item("openalex:1"))})
    service = SearchModuleService(manager, selector)

    request = SearchRequest(query="query", domains=("paper",), providers=(_provider("openalex"),))
    await service.search(request, context, _execution())

    assert selector.default_calls == 0
    assert selector.explicit_calls == 1
    assert manager.calls == [selected.adapter_id]


@pytest.mark.asyncio
async def test_explicit_multiple_providers_uses_rrf_and_merges_provenance() -> None:
    context = _context()
    first = _selection("first", priority=10)
    second = _selection("second", priority=1)
    selector = _Selector(default=(), explicit=(first, second))
    manager = _Manager(
        {
            first.adapter_id: _page(
                context,
                _item("first-doi", title="Shared", provider="first", rank=1, doi="10.1/shared"),
                _item("first-only", provider="first", rank=2),
            ),
            second.adapter_id: _page(
                context,
                _item(
                    "second-doi", title="Different", provider="second", rank=2, doi="10.1/shared"
                ),
                _item("second-only", provider="second", rank=1),
            ),
        }
    )
    service = SearchModuleService(manager, selector)
    request = SearchRequest(
        query="query",
        domains=("paper",),
        providers=(_provider("first"), _provider("second")),
    )

    result = await service.search(request, context, _execution())

    assert manager.calls == [first.adapter_id, second.adapter_id]
    assert [item.id for item in result.items] == ["first-doi", "second-only", "first-only"]
    assert [entry.provider for entry in result.items[0].provenance] == ["first", "second"]
    assert result.meta == SearchMeta(
        requested=("first", "second"),
        succeeded=("first", "second"),
    )


@pytest.mark.asyncio
async def test_ties_use_yaml_priority_then_provider_local_rank_then_canonical_id() -> None:
    context = _context()
    high_priority = _selection("higher-priority", priority=1)
    low_priority = _selection("lower-priority", priority=9)
    selector = _Selector(default=(), explicit=(low_priority, high_priority))
    manager = _Manager(
        {
            low_priority.adapter_id: _page(
                context, _item("zeta", rank=1, provider="lower-priority")
            ),
            high_priority.adapter_id: _page(
                context, _item("beta", rank=1, provider="higher-priority")
            ),
        }
    )
    service = SearchModuleService(manager, selector)
    request = SearchRequest(
        query="query",
        domains=("paper",),
        providers=(_provider("lower-priority"), _provider("higher-priority")),
    )

    result = await service.search(request, context, _execution())

    assert [item.id for item in result.items] == ["beta", "zeta"]

    same_priority = _Selector(default=(), explicit=(low_priority, _selection("other", priority=9)))
    same_priority_manager = _Manager(
        {
            low_priority.adapter_id: _page(
                context, _item("zeta", rank=1, provider="lower-priority")
            ),
            "other-adapter": _page(context, _item("alpha", rank=1, provider="other")),
        }
    )
    canonical_result = await SearchModuleService(same_priority_manager, same_priority).search(
        SearchRequest(
            query="query",
            domains=("paper",),
            providers=(_provider("lower-priority"), _provider("other")),
        ),
        context,
        _execution(),
    )
    assert [item.id for item in canonical_result.items] == ["alpha", "zeta"]


@pytest.mark.asyncio
async def test_url_and_normalized_title_year_are_deduplication_fallbacks() -> None:
    context = _context()
    first = _selection("first")
    second = _selection("second")
    selector = _Selector(default=(), explicit=(first, second))
    manager = _Manager(
        {
            first.adapter_id: _page(
                context,
                _item("url-one", provider="first", url="https://example.com/same"),
                _item(
                    "title-one",
                    title=" A  normalized title ",
                    provider="first",
                    rank=2,
                    year=2024,
                ),
            ),
            second.adapter_id: _page(
                context,
                _item("url-two", provider="second", url="https://example.com/same"),
                _item(
                    "title-two",
                    title="a normalized title",
                    provider="second",
                    rank=2,
                    year=2024,
                ),
            ),
        }
    )
    request = SearchRequest(
        query="query",
        domains=("paper",),
        providers=(_provider("first"), _provider("second")),
    )

    result = await SearchModuleService(manager, selector).search(request, context, _execution())

    assert [item.id for item in result.items] == ["url-one", "title-one"]
    assert all(len(item.provenance) == 2 for item in result.items)


@pytest.mark.asyncio
async def test_any_success_returns_partial_page_with_safe_failed_provider_details() -> None:
    context = _context()
    healthy = _selection("healthy")
    failed = _selection("failed")
    selector = _Selector(default=(), explicit=(healthy, failed))
    manager = _Manager(
        {
            healthy.adapter_id: _page(context, _item("healthy-item", provider="healthy")),
            failed.adapter_id: ProviderError(ProviderErrorCode.DEADLINE_EXCEEDED),
        }
    )
    request = SearchRequest(
        query="query",
        domains=("paper",),
        providers=(_provider("healthy"), _provider("failed")),
    )

    result = await SearchModuleService(manager, selector).search(request, context, _execution())

    assert result.meta == SearchMeta(
        partial=True,
        requested=("healthy", "failed"),
        succeeded=("healthy",),
        failed=(ProviderFailure(provider="failed", code="provider_timeout"),),
    )


@pytest.mark.asyncio
async def test_explicit_multi_provider_dispatch_is_concurrent() -> None:
    context = _context()
    first = _selection("first")
    second = _selection("second")
    both_started = asyncio.Event()

    class ConcurrentManager:
        def __init__(self) -> None:
            self.started = 0

        async def execute(self, adapter_id, request, request_context, execution):  # noqa: ANN001
            self.started += 1
            if self.started == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.5)
            return _page(context, _item(adapter_id, provider=adapter_id))

    manager = ConcurrentManager()
    request = SearchRequest(
        query="query",
        domains=("paper",),
        providers=(_provider("first"), _provider("second")),
    )

    result = await SearchModuleService(
        manager, _Selector(default=(), explicit=(first, second))
    ).search(request, context, _execution())

    assert manager.started == 2
    assert len(result.items) == 2


@pytest.mark.asyncio
async def test_all_failures_raise_typed_canonical_provider_error() -> None:
    context = _context()
    first = _selection("first")
    second = _selection("second")
    manager = _Manager(
        {
            first.adapter_id: ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE),
            second.adapter_id: ProviderError(ProviderErrorCode.INVALID_UPSTREAM_RESPONSE),
        }
    )
    request = SearchRequest(
        query="query",
        domains=("paper",),
        providers=(_provider("first"), _provider("second")),
    )

    with pytest.raises(ProviderError) as exc_info:
        await SearchModuleService(manager, _Selector(default=(), explicit=(first, second))).search(
            request, context, _execution()
        )
    assert exc_info.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE

    timeout_manager = _Manager(
        {
            first.adapter_id: ProviderError(ProviderErrorCode.DEADLINE_EXCEEDED),
            second.adapter_id: ProviderError(ProviderErrorCode.DEADLINE_EXCEEDED),
        }
    )
    with pytest.raises(ProviderError) as timeout_error:
        await SearchModuleService(
            timeout_manager, _Selector(default=(), explicit=(first, second))
        ).search(request, context, _execution())
    assert timeout_error.value.code is ProviderErrorCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_single_provider_failure_preserves_public_retry_metadata() -> None:
    context = _context()
    primary = _selection("crossref")
    upstream = ProviderError(
        ProviderErrorCode.RATE_LIMITED,
        provider_id="crossref",
        retry_after_seconds=17,
    )
    manager = _Manager({primary.adapter_id: upstream})

    with pytest.raises(ProviderError) as caught:
        await SearchModuleService(manager, _Selector(default=(primary,))).search(
            SearchRequest(query="query", domains=("paper",)),
            context,
            _execution(),
        )

    assert caught.value.code is ProviderErrorCode.RATE_LIMITED
    assert caught.value.provider_id == "crossref"
    assert caught.value.retry_after_seconds == 17


@pytest.mark.asyncio
async def test_default_selection_count_and_cancel_or_deadline_stop_before_manager_call() -> None:
    context = _context()
    first = _selection("first")
    second = _selection("second")
    manager = _Manager({})
    service = SearchModuleService(manager, _Selector(default=(first, second)))

    with pytest.raises(ProviderError) as selection_error:
        await service.search(
            SearchRequest(query="query", domains=("paper",)), context, _execution()
        )
    assert selection_error.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert manager.calls == []

    cancel_event = asyncio.Event()
    cancel_event.set()
    with pytest.raises(ProviderError) as cancelled:
        await SearchModuleService(manager, _Selector(default=(first,))).search(
            SearchRequest(query="query", domains=("paper",)),
            context,
            ExecutionContext.with_timeout(30, cancel_event=cancel_event),
        )
    assert cancelled.value.code is ProviderErrorCode.CANCELLED

    with pytest.raises(ProviderError) as expired:
        await SearchModuleService(manager, _Selector(default=(first,))).search(
            SearchRequest(query="query", domains=("paper",)),
            context,
            ExecutionContext(deadline_monotonic=time.monotonic() - 1),
        )
    assert expired.value.code is ProviderErrorCode.DEADLINE_EXCEEDED
    assert manager.calls == []
