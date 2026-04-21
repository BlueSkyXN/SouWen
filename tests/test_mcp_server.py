"""MCP Server 集成工具单元测试

覆盖 souwen.integrations.mcp_server.handle_tool_call 中的以下工具：
- fetch_paper_details（semantic_scholar / crossref / 未知源 / 默认源）
- search_by_topic（无日期过滤 / 仅 year_start / 仅 year_end / 两端均指定 / 单源失败容错）

不依赖 MCP SDK，直接测试模块级 handle_tool_call 函数。
使用 unittest.mock 模拟客户端，不需要真实 API Key 或网络访问。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from souwen.integrations.mcp_server import (
    _MONTH_END,
    _MONTH_START,
    _YEAR_MAX,
    _YEAR_MIN,
    handle_tool_call,
)
from souwen.models import Author, PaperResult, SearchResponse, SourceType


# ── 通用辅助 ─────────────────────────────────────────────────


def _make_paper(source: SourceType = SourceType.SEMANTIC_SCHOLAR) -> PaperResult:
    """构造最小有效 PaperResult，用于 mock 返回。"""
    return PaperResult(
        source=source,
        title="Test Paper",
        authors=[Author(name="Alice")],
        abstract="An abstract.",
        doi="10.1234/test",
        year=2023,
        publication_date=date(2023, 6, 1),
        source_url="https://example.com/paper/1",
        pdf_url="https://example.com/paper/1.pdf",
        tldr="Short summary.",
        raw={},
    )


def _make_search_response(
    source: SourceType = SourceType.ARXIV, n: int = 2
) -> SearchResponse:
    """构造包含 n 篇论文的 SearchResponse。"""
    papers = [
        PaperResult(
            source=source,
            title=f"Paper {i}",
            authors=[Author(name=f"Author {i}")],
            source_url=f"https://example.com/{i}",
            raw={},
        )
        for i in range(n)
    ]
    return SearchResponse(
        query="test topic",
        source=source,
        total_results=n,
        results=papers,
    )


def _make_mock_client(
    search_resp: SearchResponse | None = None,
    get_paper_resp: PaperResult | None = None,
    get_by_doi_resp: PaperResult | None = None,
    side_effect: Exception | None = None,
) -> AsyncMock:
    """构造带 async context manager 的 mock 客户端。"""
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)

    if side_effect:
        if search_resp is not None:
            mock.search = AsyncMock(side_effect=side_effect)
        if get_paper_resp is not None:
            mock.get_paper = AsyncMock(side_effect=side_effect)
        if get_by_doi_resp is not None:
            mock.get_by_doi = AsyncMock(side_effect=side_effect)
    else:
        if search_resp is not None:
            mock.search = AsyncMock(return_value=search_resp)
        if get_paper_resp is not None:
            mock.get_paper = AsyncMock(return_value=get_paper_resp)
        if get_by_doi_resp is not None:
            mock.get_by_doi = AsyncMock(return_value=get_by_doi_resp)

    return mock


# ── fetch_paper_details ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_paper_details_semantic_scholar():
    """semantic_scholar 源返回完整 PaperResult JSON（含 tldr）。"""
    paper = _make_paper(SourceType.SEMANTIC_SCHOLAR)
    mock_client = _make_mock_client(get_paper_resp=paper)

    with patch("souwen.paper.semantic_scholar.SemanticScholarClient", return_value=mock_client):
        result = await handle_tool_call(
            "fetch_paper_details", {"paper_id": "abc123", "source": "semantic_scholar"}
        )

    assert result["title"] == "Test Paper"
    assert result["source"] == "semantic_scholar"
    assert result["tldr"] == "Short summary."
    mock_client.get_paper.assert_awaited_once_with("abc123")


@pytest.mark.asyncio
async def test_fetch_paper_details_crossref():
    """crossref 源返回正确的 PaperResult JSON。"""
    paper = _make_paper(SourceType.CROSSREF)
    mock_client = _make_mock_client(get_by_doi_resp=paper)

    with patch("souwen.paper.crossref.CrossrefClient", return_value=mock_client):
        result = await handle_tool_call(
            "fetch_paper_details", {"paper_id": "10.1234/test", "source": "crossref"}
        )

    assert result["source"] == "crossref"
    mock_client.get_by_doi.assert_awaited_once_with("10.1234/test")


@pytest.mark.asyncio
async def test_fetch_paper_details_unknown_source():
    """未知数据源应返回包含 error 和 supported_sources 的 dict（不崩溃）。"""
    result = await handle_tool_call(
        "fetch_paper_details", {"paper_id": "abc", "source": "unknown_db"}
    )

    assert isinstance(result, dict)
    assert "error" in result
    assert "supported_sources" in result
    assert "semantic_scholar" in result["supported_sources"]
    assert "crossref" in result["supported_sources"]


@pytest.mark.asyncio
async def test_fetch_paper_details_default_source_is_semantic_scholar():
    """不传 source 时默认走 semantic_scholar。"""
    paper = _make_paper(SourceType.SEMANTIC_SCHOLAR)
    mock_client = _make_mock_client(get_paper_resp=paper)

    with patch("souwen.paper.semantic_scholar.SemanticScholarClient", return_value=mock_client):
        result = await handle_tool_call("fetch_paper_details", {"paper_id": "xyz"})

    mock_client.get_paper.assert_awaited_once_with("xyz")
    assert result["source"] == "semantic_scholar"


# ── search_by_topic ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_by_topic_no_date_filter():
    """无日期过滤时正常聚合所有源结果，arXiv 收到 date_from=None。"""
    arxiv_resp = _make_search_response(SourceType.ARXIV, n=2)
    s2_resp = _make_search_response(SourceType.SEMANTIC_SCHOLAR, n=1)
    crossref_resp = _make_search_response(SourceType.CROSSREF, n=1)

    mock_arxiv = _make_mock_client(search_resp=arxiv_resp)
    mock_s2 = _make_mock_client(search_resp=s2_resp)
    mock_crossref = _make_mock_client(search_resp=crossref_resp)

    with (
        patch("souwen.paper.arxiv.ArxivClient", return_value=mock_arxiv),
        patch("souwen.paper.semantic_scholar.SemanticScholarClient", return_value=mock_s2),
        patch("souwen.paper.crossref.CrossrefClient", return_value=mock_crossref),
    ):
        result = await handle_tool_call("search_by_topic", {"topic": "machine learning"})

    assert isinstance(result, list)
    assert len(result) == 4  # 2 arXiv + 1 S2 + 1 Crossref

    # arXiv 无日期过滤时 date_from/date_to 均为 None
    arxiv_kwargs = mock_arxiv.search.call_args.kwargs
    assert arxiv_kwargs.get("date_from") is None
    assert arxiv_kwargs.get("date_to") is None


@pytest.mark.asyncio
async def test_search_by_topic_with_year_start_only():
    """只指定 year_start 时各源收到正确的起始过滤参数。"""
    arxiv_resp = _make_search_response(SourceType.ARXIV, n=1)
    s2_resp = _make_search_response(SourceType.SEMANTIC_SCHOLAR, n=0)
    crossref_resp = _make_search_response(SourceType.CROSSREF, n=0)

    mock_arxiv = _make_mock_client(search_resp=arxiv_resp)
    mock_s2 = _make_mock_client(search_resp=s2_resp)
    mock_crossref = _make_mock_client(search_resp=crossref_resp)

    with (
        patch("souwen.paper.arxiv.ArxivClient", return_value=mock_arxiv),
        patch("souwen.paper.semantic_scholar.SemanticScholarClient", return_value=mock_s2),
        patch("souwen.paper.crossref.CrossrefClient", return_value=mock_crossref),
    ):
        await handle_tool_call(
            "search_by_topic", {"topic": "deep learning", "year_start": 2022}
        )

    # arXiv: date_from=2022-01-01, date_to=None
    arxiv_kwargs = mock_arxiv.search.call_args.kwargs
    assert arxiv_kwargs["date_from"] == f"2022{_MONTH_START}"
    assert arxiv_kwargs["date_to"] is None

    # Semantic Scholar: query 中含 year:2022-{YEAR_MAX}
    s2_args = mock_s2.search.call_args
    s2_query = s2_args.args[0] if s2_args.args else s2_args.kwargs.get("query", "")
    assert f"year:2022-{_YEAR_MAX}" in s2_query

    # Crossref: filters 含 from-pub-date, 不含 until-pub-date
    crossref_kwargs = mock_crossref.search.call_args.kwargs
    filters = crossref_kwargs.get("filters") or {}
    assert filters.get("from-pub-date") == "2022"
    assert "until-pub-date" not in filters


@pytest.mark.asyncio
async def test_search_by_topic_with_year_end_only():
    """只指定 year_end 时各源收到正确的结束过滤参数。"""
    arxiv_resp = _make_search_response(SourceType.ARXIV, n=0)
    s2_resp = _make_search_response(SourceType.SEMANTIC_SCHOLAR, n=0)
    crossref_resp = _make_search_response(SourceType.CROSSREF, n=0)

    mock_arxiv = _make_mock_client(search_resp=arxiv_resp)
    mock_s2 = _make_mock_client(search_resp=s2_resp)
    mock_crossref = _make_mock_client(search_resp=crossref_resp)

    with (
        patch("souwen.paper.arxiv.ArxivClient", return_value=mock_arxiv),
        patch("souwen.paper.semantic_scholar.SemanticScholarClient", return_value=mock_s2),
        patch("souwen.paper.crossref.CrossrefClient", return_value=mock_crossref),
    ):
        await handle_tool_call(
            "search_by_topic", {"topic": "nlp", "year_end": 2021}
        )

    # arXiv: date_from=None, date_to=2021-12-31
    arxiv_kwargs = mock_arxiv.search.call_args.kwargs
    assert arxiv_kwargs["date_from"] is None
    assert arxiv_kwargs["date_to"] == f"2021{_MONTH_END}"

    # Semantic Scholar: query 中含 year:{YEAR_MIN}-2021
    s2_args = mock_s2.search.call_args
    s2_query = s2_args.args[0] if s2_args.args else s2_args.kwargs.get("query", "")
    assert f"year:{_YEAR_MIN}-2021" in s2_query

    # Crossref: filters 含 until-pub-date, 不含 from-pub-date
    crossref_kwargs = mock_crossref.search.call_args.kwargs
    filters = crossref_kwargs.get("filters") or {}
    assert filters.get("until-pub-date") == "2021"
    assert "from-pub-date" not in filters


@pytest.mark.asyncio
async def test_search_by_topic_with_both_years():
    """同时指定 year_start 和 year_end 时各源收到正确的双端过滤参数。"""
    arxiv_resp = _make_search_response(SourceType.ARXIV, n=0)
    s2_resp = _make_search_response(SourceType.SEMANTIC_SCHOLAR, n=0)
    crossref_resp = _make_search_response(SourceType.CROSSREF, n=0)

    mock_arxiv = _make_mock_client(search_resp=arxiv_resp)
    mock_s2 = _make_mock_client(search_resp=s2_resp)
    mock_crossref = _make_mock_client(search_resp=crossref_resp)

    with (
        patch("souwen.paper.arxiv.ArxivClient", return_value=mock_arxiv),
        patch("souwen.paper.semantic_scholar.SemanticScholarClient", return_value=mock_s2),
        patch("souwen.paper.crossref.CrossrefClient", return_value=mock_crossref),
    ):
        await handle_tool_call(
            "search_by_topic",
            {"topic": "transformer", "year_start": 2020, "year_end": 2023},
        )

    # arXiv
    arxiv_kwargs = mock_arxiv.search.call_args.kwargs
    assert arxiv_kwargs["date_from"] == f"2020{_MONTH_START}"
    assert arxiv_kwargs["date_to"] == f"2023{_MONTH_END}"

    # Semantic Scholar
    s2_args = mock_s2.search.call_args
    s2_query = s2_args.args[0] if s2_args.args else s2_args.kwargs.get("query", "")
    assert "year:2020-2023" in s2_query

    # Crossref
    crossref_kwargs = mock_crossref.search.call_args.kwargs
    filters = crossref_kwargs.get("filters") or {}
    assert filters.get("from-pub-date") == "2020"
    assert filters.get("until-pub-date") == "2023"


@pytest.mark.asyncio
async def test_search_by_topic_source_error_does_not_stop_others():
    """单个源失败时不阻止其他源的结果，失败条目含 error 字段。"""
    good_resp = _make_search_response(SourceType.CROSSREF, n=2)

    mock_arxiv = _make_mock_client(
        search_resp=_make_search_response(SourceType.ARXIV, n=0),
        side_effect=RuntimeError("arXiv is down"),
    )
    mock_crossref = _make_mock_client(search_resp=good_resp)

    with (
        patch("souwen.paper.arxiv.ArxivClient", return_value=mock_arxiv),
        patch("souwen.paper.crossref.CrossrefClient", return_value=mock_crossref),
    ):
        result = await handle_tool_call(
            "search_by_topic",
            {"topic": "quantum computing", "sources": ["arxiv", "crossref"]},
        )

    # arXiv 失败 → 1 个错误条目；crossref 成功 → 2 篇论文
    assert len(result) == 3
    error_items = [d for d in result if "error" in d]
    paper_items = [d for d in result if "title" in d]
    assert len(error_items) == 1
    assert len(paper_items) == 2
    assert error_items[0]["source"] == "arxiv"
    assert "RuntimeError" in error_items[0]["error"]


@pytest.mark.asyncio
async def test_handle_tool_call_unknown_tool():
    """未知工具名返回包含 'Unknown tool' 的字符串，不崩溃。"""
    result = await handle_tool_call("nonexistent_tool", {})
    assert isinstance(result, str)
    assert "Unknown tool" in result
    assert "nonexistent_tool" in result
