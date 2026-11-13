"""Deterministic tests for the compact search projection and text formats."""

from __future__ import annotations

import pytest

from souwen.modules.search.application.projection import (
    format_search_error,
    format_search_summary,
    project_search_page,
)
from souwen.platform.provider_spi import (
    ExecutionContext,
    PageInfo,
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)


def _page(
    items: tuple[SearchItem, ...],
    *,
    succeeded: tuple[str, ...] = ("openalex",),
    failed: tuple[ProviderFailure, ...] = (),
) -> SearchPage:
    return SearchPage(
        items=items,
        page=PageInfo(limit=8),
        meta=SearchMeta(
            partial=bool(failed),
            requested=succeeded + tuple(item.provider for item in failed),
            succeeded=succeeded,
            failed=failed,
        ),
        context=RequestContext(request_id="projection-test"),
    )


def _item(title: str, url: str, *, snippet: str | None = None, attributes=None) -> SearchItem:
    return SearchItem(
        id=f"id:{title}",
        title=title,
        url=url,
        snippet=snippet,
        provenance=(Provenance(provider="openalex", outcome="success"),),
        attributes=attributes,
    )


def test_project_page_flattens_items_and_names_sources() -> None:
    page = _page(
        (
            _item(
                "Attention Is All You Need",
                "https://arxiv.org/abs/1706.03762",
                snippet="We propose the Transformer.",
                attributes=SearchAttributes(
                    year=2017, authors=("Vaswani", "Shazeer", "Parmar", "Uszkoreit")
                ),
            ),
            _item("Plain hit", "https://example.com/a"),
        )
    )

    summary = project_search_page(page)

    assert summary.sources == ("openalex",)
    assert summary.partial is False
    first, second = summary.results
    assert first.title == "Attention Is All You Need"
    assert first.year == 2017
    assert first.authors == ("Vaswani", "Shazeer", "Parmar", "Uszkoreit")
    assert first.url == "https://arxiv.org/abs/1706.03762"
    assert second.year is None and second.authors == ()
    assert second.snippet is None


def test_format_summary_renders_numbered_items_with_paper_metadata() -> None:
    page = _page(
        (
            _item(
                "Attention Is All You Need",
                "https://arxiv.org/abs/1706.03762",
                snippet="We propose the Transformer.",
                attributes=SearchAttributes(year=2017, authors=("Vaswani", "Shazeer")),
            ),
            _item("Plain hit", "https://example.com/a", snippet="short"),
        )
    )

    text = format_search_summary(project_search_page(page))

    lines = text.splitlines()
    assert lines[0] == "1. Attention Is All You Need (2017) — Vaswani, Shazeer"
    assert lines[1] == "   https://arxiv.org/abs/1706.03762"
    assert lines[2] == "   We propose the Transformer."
    assert lines[3] == "2. Plain hit"
    assert text.endswith("results from: openalex")


def test_format_summary_marks_partial_and_caps_author_list() -> None:
    page = _page(
        (_item("Hit", "https://example.com/h"),),
        succeeded=("openalex",),
        failed=(ProviderFailure(provider="crossref", code="rate_limited"),),
    )

    text = format_search_summary(project_search_page(page))

    assert text.endswith("results from: openalex (partial: some sources failed)")


def test_format_summary_empty_results_is_actionable() -> None:
    text = format_search_summary(project_search_page(_page(())))

    assert text.startswith("No results.")


def test_format_error_lists_every_failed_source_with_category() -> None:
    error = ProviderError(
        ProviderErrorCode.PROVIDER_UNAVAILABLE,
        failures=(
            ProviderFailure(provider="huggingface", code="rate_limited"),
            ProviderFailure(provider="crossref", code="provider_unavailable"),
        ),
    )

    text = format_search_error(error)

    assert "huggingface: rate_limited" in text
    assert "crossref: provider_unavailable" in text
    assert "To proceed:" in text


def test_format_error_single_provider_falls_back_to_provider_id() -> None:
    error = ProviderError(ProviderErrorCode.RATE_LIMITED, provider_id="crossref")

    text = format_search_error(error)

    assert "crossref: rate_limited" in text
    assert "wait a moment and retry" in text


@pytest.mark.asyncio
async def test_all_fail_error_carries_per_source_failures() -> None:
    """The search service must raise with the per-source failure list attached."""

    from souwen.modules.search.application.orchestration import (
        OrderedSearchProviderSelector,
        SearchModuleService,
        SearchProviderSelection,
    )
    from souwen.platform.provider_spi import ProviderRef

    class _FailingManager:
        async def execute(self, adapter_id, request, request_context, execution):
            if adapter_id == "one-search":
                raise ProviderError(ProviderErrorCode.RATE_LIMITED)
            raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE)

    selection_one = SearchProviderSelection(
        provider=ProviderRef(id="one", kind="search"), adapter_id="one-search", yaml_priority=1
    )
    selection_two = SearchProviderSelection(
        provider=ProviderRef(id="two", kind="search"), adapter_id="two-search", yaml_priority=2
    )
    selector = OrderedSearchProviderSelector({"paper": (selection_one, selection_two)})
    service = SearchModuleService(_FailingManager(), selector, request_budget=5)

    with pytest.raises(ProviderError) as exc_info:
        await service.search(
            SearchRequest(query="q", domains=("paper",)),
            RequestContext(request_id="r"),
            ExecutionContext.with_timeout(5),
        )

    failures = exc_info.value.failures
    assert tuple(failure.provider for failure in failures) == ("one", "two")
    assert tuple(failure.code for failure in failures) == ("rate_limited", "provider_unavailable")
