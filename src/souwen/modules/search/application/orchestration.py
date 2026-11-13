"""Canonical Search orchestration through injected Provider v2 ports.

Owner: Search Core. Inputs: canonical Search request/context/execution values.
Outputs: one canonical SearchPage or a safe typed ProviderError. Dependencies:
the Search Provider SPI only; concrete providers, legacy registry, and delivery
frameworks are intentionally outside this module.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    ProviderRef,
    Provenance,
    RequestContext,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)


RRF_K = 60
DEFAULT_BATCH_SIZE = 3
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 10.0
DEFAULT_FAILURES_BEFORE_DEMOTION = 3
DEFAULT_DEMOTION_SECONDS = 600.0
DEFAULT_REQUEST_BUDGET_SECONDS = 25.0


@dataclass(frozen=True, slots=True)
class SearchProviderSelection:
    """One selected search adapter and its YAML ordering priority."""

    provider: ProviderRef
    adapter_id: str
    yaml_priority: int

    def __post_init__(self) -> None:
        if self.provider.kind != "search":
            raise ValueError("Search provider selection must use kind='search'")
        if not self.adapter_id:
            raise ValueError("adapter_id must not be blank")


class SearchProviderSelector(Protocol):
    """Resolve public provider refs to eligible adapter selections.

    The selector is the single boundary for the YAML domain/capability ordered
    default. ``select_default`` returns the whole ordered candidate list.
    """

    def select_default(self, request: SearchRequest) -> tuple[SearchProviderSelection, ...]:
        """Return every candidate for the domain, YAML priority first."""

    def select_explicit(
        self, providers: tuple[ProviderRef, ...]
    ) -> tuple[SearchProviderSelection, ...]:
        """Resolve only the caller's explicitly requested provider IDs."""


class OrderedSearchProviderSelector:
    """Immutable projection of YAML domain/capability provider priority."""

    def __init__(
        self,
        selections_by_domain: Mapping[str, tuple[SearchProviderSelection, ...]],
        *,
        explicit_selections: tuple[SearchProviderSelection, ...] = (),
    ) -> None:
        ordered: dict[str, tuple[SearchProviderSelection, ...]] = {}
        by_provider: dict[str, SearchProviderSelection] = {}
        for domain, selections in selections_by_domain.items():
            if not domain:
                raise ValueError("each Search domain must have at least one provider selection")
            if not selections:
                # 领域暂时没有可用源（体检判死且无候选）：跳过而非报错，P2 领域收敛会从 domain 取值里去掉
                continue
            ranked = tuple(
                selection
                for _index, selection in sorted(
                    enumerate(selections),
                    key=lambda item: (item[1].yaml_priority, item[0]),
                )
            )
            provider_ids = tuple(selection.provider.id for selection in ranked)
            if len(provider_ids) != len(set(provider_ids)):
                raise ValueError("provider selection IDs must be unique within a domain")
            ordered[domain] = ranked
            for selection in ranked:
                existing = by_provider.get(selection.provider.id)
                if existing is not None and existing != selection:
                    raise ValueError(
                        "a provider ID must resolve to one immutable adapter selection"
                    )
                by_provider[selection.provider.id] = selection
        explicit_ids = tuple(selection.provider.id for selection in explicit_selections)
        if len(explicit_ids) != len(set(explicit_ids)):
            raise ValueError("explicit-only provider selection IDs must be unique")
        for selection in explicit_selections:
            existing = by_provider.get(selection.provider.id)
            if existing is not None and existing != selection:
                raise ValueError("a provider ID must resolve to one immutable adapter selection")
            by_provider[selection.provider.id] = selection
        self._by_domain = ordered
        self._by_provider = by_provider

    def select_default(self, request: SearchRequest) -> tuple[SearchProviderSelection, ...]:
        if len(request.domains) != 1:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST)
        selections = self._by_domain.get(request.domains[0], ())
        if not selections:
            raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE)
        return selections

    def select_explicit(
        self, providers: tuple[ProviderRef, ...]
    ) -> tuple[SearchProviderSelection, ...]:
        selections: list[SearchProviderSelection] = []
        for provider in providers:
            selection = self._by_provider.get(provider.id)
            if selection is None or provider.kind != "search":
                raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE)
            selections.append(selection)
        return tuple(selections)


class SearchProviderManager(Protocol):
    """Minimal manager port used by Search Core; concrete construction stays Platform-owned."""

    async def execute(
        self,
        adapter_id: str,
        request: SearchRequest,
        request_context: RequestContext,
        execution: ExecutionContext,
    ) -> SearchPage:
        """Call the selected adapter solely through the Provider Manager."""


@dataclass(slots=True)
class _Aggregate:
    item: SearchItem
    score: float
    yaml_priority: int
    local_rank: int
    canonical_id: str
    provenance: list[Provenance] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _ProviderOutcome:
    selection: SearchProviderSelection
    page: SearchPage | None = None
    error: ProviderError | None = None


class SearchModuleService:
    """Concrete canonical SearchModule implementing primary selection and explicit fanout."""

    def __init__(
        self,
        manager: SearchProviderManager,
        selector: SearchProviderSelector,
        *,
        provider_timeout: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        request_budget: float = DEFAULT_REQUEST_BUDGET_SECONDS,
        demote_after: int = DEFAULT_FAILURES_BEFORE_DEMOTION,
        demote_seconds: float = DEFAULT_DEMOTION_SECONDS,
    ) -> None:
        self._manager = manager
        self._selector = selector
        self._provider_timeout = provider_timeout
        self._request_budget = request_budget
        self._demote_after = demote_after
        self._demote_seconds = demote_seconds
        self._consecutive_failures: dict[str, int] = {}
        self._demoted_until: dict[str, float] = {}

    async def search(
        self,
        request: SearchRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> SearchPage:
        """Execute one selected provider or explicitly requested multi-provider fanout."""

        execution.raise_if_cancelled_or_expired()
        selections = self._order_for_memory(self._select(request))
        outcomes: list[_ProviderOutcome] = []
        # 点名源时一次跑完；不点名时每批 3 个，凑够结果或全部失败再取下一批。
        batched = request.providers is None and len(selections) > DEFAULT_BATCH_SIZE
        batches = (
            [
                selections[index : index + DEFAULT_BATCH_SIZE]
                for index in range(0, len(selections), DEFAULT_BATCH_SIZE)
            ]
            if batched
            else [selections]
        )
        wanted = request.page.limit if request.page is not None else 8
        deadline = time.monotonic() + self._request_budget
        unrun: list[SearchProviderSelection] = []
        for index, batch in enumerate(batches):
            if time.monotonic() >= deadline:
                unrun.extend(selection for later in batches[index:] for selection in later)
                break
            execution.raise_if_cancelled_or_expired()
            outcomes.extend(await self._run_batch(batch, request, context, execution))
            got = sum(len(outcome.page.items) for outcome in outcomes if outcome.page is not None)
            self._remember(outcomes[-len(batch) :])
            if not batched or got >= wanted:
                break
        outcomes.extend(
            _ProviderOutcome(
                selection=selection,
                error=ProviderError(ProviderErrorCode.DEADLINE_EXCEEDED),
            )
            for selection in unrun
        )

        successes: list[tuple[SearchProviderSelection, SearchPage]] = []
        failures: list[ProviderFailure] = []
        errors: list[ProviderError] = []
        for outcome in outcomes:
            if outcome.page is not None:
                successes.append((outcome.selection, outcome.page))
                continue
            error = outcome.error or ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE)
            errors.append(error)
            failures.append(
                ProviderFailure(
                    provider=outcome.selection.provider.id,
                    code=_canonical_failure_code(error.code),
                )
            )

        if not successes:
            raise _all_fail_error(errors, failures)

        items = _merge_items(successes)
        first_page = successes[0][1].page
        # A provider cursor is meaningful only for that provider. Explicit
        # fanout deliberately does not expose one provider's continuation as a
        # canonical multi-provider cursor.
        page = (
            first_page
            if len(successes) == 1
            else first_page.model_copy(update={"next_cursor": None, "total": None})
        )
        return SearchPage(
            items=items,
            page=page,
            meta=SearchMeta(
                partial=bool(failures),
                requested=tuple(selection.provider.id for selection in selections),
                succeeded=tuple(selection.provider.id for selection, _page in successes),
                failed=tuple(failures),
            ),
            context=context,
        )

    async def _run_batch(
        self,
        batch: tuple[SearchProviderSelection, ...],
        request: SearchRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> list[_ProviderOutcome]:
        """Run one batch concurrently and turn a hung source into a typed timeout."""

        tasks = [
            asyncio.create_task(self._execute_selection(selection, request, context, execution))
            for selection in batch
        ]
        done, pending = await asyncio.wait(tasks, timeout=self._provider_timeout)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        outcomes: list[_ProviderOutcome] = []
        for selection, task in zip(batch, tasks, strict=True):
            if task in pending or task.cancelled():
                outcomes.append(
                    _ProviderOutcome(
                        selection=selection,
                        error=ProviderError(ProviderErrorCode.DEADLINE_EXCEEDED),
                    )
                )
                continue
            result = task.result()
            outcomes.append(
                result
                if isinstance(result, _ProviderOutcome)
                else _ProviderOutcome(
                    selection=selection,
                    error=ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE),
                )
            )
        return outcomes

    async def _execute_selection(
        self,
        selection: SearchProviderSelection,
        request: SearchRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> _ProviderOutcome:
        execution.raise_if_cancelled_or_expired()
        try:
            page = await self._manager.execute(selection.adapter_id, request, context, execution)
        except ProviderError as error:
            return _ProviderOutcome(selection=selection, error=error)
        except Exception:
            # Platform diagnostics remain Platform-owned; Core exposes only a safe outcome.
            return _ProviderOutcome(
                selection=selection,
                error=ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE),
            )
        return _ProviderOutcome(selection=selection, page=page)

    def _order_for_memory(
        self, selections: tuple[SearchProviderSelection, ...]
    ) -> tuple[SearchProviderSelection, ...]:
        now = time.monotonic()
        active = [
            selection
            for selection in selections
            if self._demoted_until.get(selection.provider.id, 0.0) <= now
        ]
        demoted = [selection for selection in selections if selection not in active]
        return tuple(active + demoted)

    def _remember(self, outcomes: list[_ProviderOutcome]) -> None:
        now = time.monotonic()
        for outcome in outcomes:
            provider_id = outcome.selection.provider.id
            if outcome.page is not None:
                self._consecutive_failures.pop(provider_id, None)
                self._demoted_until.pop(provider_id, None)
                continue
            failures = self._consecutive_failures.get(provider_id, 0) + 1
            self._consecutive_failures[provider_id] = failures
            if failures >= self._demote_after:
                self._demoted_until[provider_id] = now + self._demote_seconds
                self._consecutive_failures[provider_id] = 0

    def _select(self, request: SearchRequest) -> tuple[SearchProviderSelection, ...]:
        if request.providers is None:
            try:
                selections = self._selector.select_default(request)
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE) from exc
            if not selections:
                raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE)
            return selections

        try:
            selections = self._selector.select_explicit(request.providers)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE) from exc
        expected = tuple(provider.id for provider in request.providers)
        selected = tuple(selection.provider.id for selection in selections)
        if len(selections) != len(expected) or set(selected) != set(expected):
            raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE)
        return selections


def _merge_items(
    pages: list[tuple[SearchProviderSelection, SearchPage]],
) -> tuple[SearchItem, ...]:
    aggregates: list[_Aggregate] = []
    for selection, page in pages:
        for position, item in enumerate(page.items, start=1):
            local_rank = item.rank if item.rank is not None else position
            aggregate = next(
                (candidate for candidate in aggregates if _same_result(candidate.item, item)), None
            )
            contribution = 1 / (RRF_K + local_rank)
            if aggregate is None:
                aggregates.append(
                    _Aggregate(
                        item=item,
                        score=contribution,
                        yaml_priority=selection.yaml_priority,
                        local_rank=local_rank,
                        canonical_id=item.id,
                        provenance=list(item.provenance),
                    )
                )
                continue
            aggregate.score += contribution
            aggregate.yaml_priority = min(aggregate.yaml_priority, selection.yaml_priority)
            aggregate.local_rank = min(aggregate.local_rank, local_rank)
            aggregate.provenance = _merge_provenance(aggregate.provenance, item.provenance)

    ordered = sorted(
        aggregates,
        key=lambda aggregate: (
            -aggregate.score,
            aggregate.yaml_priority,
            aggregate.local_rank,
            aggregate.canonical_id,
        ),
    )
    return tuple(
        aggregate.item.model_copy(
            update={
                "rank": index,
                "provenance": tuple(aggregate.provenance),
            }
        )
        for index, aggregate in enumerate(ordered, start=1)
    )


def _same_result(left: SearchItem, right: SearchItem) -> bool:
    """Apply the approved stable-ID, URL, then normalized title/year deduplication order."""

    left_identifiers = _stable_identifiers(left)
    right_identifiers = _stable_identifiers(right)
    if left_identifiers and right_identifiers and left_identifiers.intersection(right_identifiers):
        return True
    if left.url is not None and right.url is not None and str(left.url) == str(right.url):
        return True
    return _normalized_title_year(left) == _normalized_title_year(right)


def _stable_identifiers(item: SearchItem) -> frozenset[tuple[str, str]]:
    if item.attributes is None:
        return frozenset()
    return frozenset(
        (identifier.scheme.casefold(), identifier.value.strip().casefold())
        for identifier in item.attributes.identifiers
    )


def _normalized_title_year(item: SearchItem) -> tuple[str, int | None]:
    year = item.attributes.year if item.attributes is not None else None
    normalized_title = " ".join(item.title.casefold().split())
    return normalized_title, year


def _merge_provenance(
    current: list[Provenance], incoming: tuple[Provenance, ...]
) -> list[Provenance]:
    seen = {(item.provider, item.attempt, item.outcome, item.retrieved_at) for item in current}
    for item in incoming:
        key = (item.provider, item.attempt, item.outcome, item.retrieved_at)
        if key not in seen:
            current.append(item)
            seen.add(key)
    return current


def _canonical_failure_code(code: ProviderErrorCode) -> str:
    return {
        ProviderErrorCode.INVALID_REQUEST: "invalid_request",
        ProviderErrorCode.INVALID_CONFIG: "provider_unavailable",
        ProviderErrorCode.CANCELLED: "provider_timeout",
        ProviderErrorCode.DEADLINE_EXCEEDED: "provider_timeout",
        ProviderErrorCode.RATE_LIMITED: "rate_limited",
        ProviderErrorCode.PROVIDER_UNAVAILABLE: "provider_unavailable",
        ProviderErrorCode.INVALID_UPSTREAM_RESPONSE: "provider_unavailable",
        ProviderErrorCode.POLICY_BLOCKED: "policy_blocked",
    }[code]


def _all_fail_error(errors: list[ProviderError], failures: list[ProviderFailure]) -> ProviderError:
    # 单源失败时其 code 与 provider_id 已足够描述，无需再带失败列表。
    if len(errors) == 1:
        return errors[0]
    if errors and all(error.code is ProviderErrorCode.RATE_LIMITED for error in errors):
        retry_values = [
            error.retry_after_seconds for error in errors if error.retry_after_seconds is not None
        ]
        return ProviderError(
            ProviderErrorCode.RATE_LIMITED,
            retry_after_seconds=max(retry_values) if retry_values else None,
            failures=tuple(failures),
        )
    if errors and all(error.code is ProviderErrorCode.POLICY_BLOCKED for error in errors):
        return ProviderError(ProviderErrorCode.POLICY_BLOCKED, failures=tuple(failures))
    if errors and all(
        error.code in {ProviderErrorCode.CANCELLED, ProviderErrorCode.DEADLINE_EXCEEDED}
        for error in errors
    ):
        return ProviderError(ProviderErrorCode.DEADLINE_EXCEEDED, failures=tuple(failures))
    return ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE, failures=tuple(failures))


__all__ = [
    "RRF_K",
    "OrderedSearchProviderSelector",
    "SearchModuleService",
    "SearchProviderManager",
    "SearchProviderSelection",
    "SearchProviderSelector",
]
