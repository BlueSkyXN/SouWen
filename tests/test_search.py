"""聚合搜索容错测试"""

from __future__ import annotations

import asyncio
import importlib

from souwen.models import SearchResponse, SourceType


async def test_search_papers_skips_timed_out_source(monkeypatch):
    """慢论文源超时时不应阻塞整体结果。"""
    search_mod = importlib.import_module("souwen.search")

    async def fast_source():
        return SearchResponse(
            query="test",
            source=SourceType.OPENALEX,
            results=[],
            total_results=0,
        )

    async def slow_source():
        await asyncio.sleep(0.05)
        return SearchResponse(
            query="test",
            source=SourceType.CROSSREF,
            results=[],
            total_results=0,
        )

    monkeypatch.setattr(search_mod, "_get_source_timeout_seconds", lambda: 0.01)
    monkeypatch.setitem(
        search_mod._PAPER_SOURCES, "fast_test_source", lambda q, n, **kw: fast_source()
    )
    monkeypatch.setitem(
        search_mod._PAPER_SOURCES, "slow_test_source", lambda q, n, **kw: slow_source()
    )

    resp = await search_mod.search_papers(
        "test",
        sources=["fast_test_source", "slow_test_source"],
    )

    assert len(resp) == 1
    assert resp[0].source == SourceType.OPENALEX


async def test_search_patents_skips_timed_out_source(monkeypatch):
    """慢专利源超时时不应阻塞整体结果。"""
    search_mod = importlib.import_module("souwen.search")

    async def fast_source():
        return SearchResponse(
            query="test",
            source=SourceType.PATENTSVIEW,
            results=[],
            total_results=0,
        )

    async def slow_source():
        await asyncio.sleep(0.05)
        return SearchResponse(
            query="test",
            source=SourceType.PQAI,
            results=[],
            total_results=0,
        )

    monkeypatch.setattr(search_mod, "_get_source_timeout_seconds", lambda: 0.01)
    monkeypatch.setitem(
        search_mod._PATENT_SOURCES,
        "fast_test_patent_source",
        lambda q, n, **kw: fast_source(),
    )
    monkeypatch.setitem(
        search_mod._PATENT_SOURCES,
        "slow_test_patent_source",
        lambda q, n, **kw: slow_source(),
    )

    resp = await search_mod.search_patents(
        "test",
        sources=["fast_test_patent_source", "slow_test_patent_source"],
    )

    assert len(resp) == 1
    assert resp[0].source == SourceType.PATENTSVIEW


def test_semaphore_is_per_event_loop():
    """_get_semaphore 在不同 event loop 中返回不同实例，避免跨 loop 错误"""
    search_mod = importlib.import_module("souwen.search")

    async def _fetch() -> asyncio.Semaphore:
        return search_mod._get_semaphore()

    loop1 = asyncio.new_event_loop()
    try:
        sem1 = loop1.run_until_complete(_fetch())
        sem1_again = loop1.run_until_complete(_fetch())
    finally:
        loop1.close()

    loop2 = asyncio.new_event_loop()
    try:
        sem2 = loop2.run_until_complete(_fetch())
    finally:
        loop2.close()

    assert sem1 is sem1_again
    assert sem1 is not sem2
