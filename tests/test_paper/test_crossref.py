"""Crossref API 客户端单元测试（pytest-httpx mock）"""

from __future__ import annotations
import re
from datetime import date

import pytest
from pytest_httpx import HTTPXMock

from souwen.paper.crossref import CrossrefClient
from souwen.models import SourceType


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

CROSSREF_SEARCH_RESPONSE = {
    "status": "ok",
    "message-type": "work-list",
    "message": {
        "total-results": 42,
        "items": [
            {
                "DOI": "10.1038/s41586-021-03819-2",
                "title": ["Highly accurate protein structure prediction"],
                "author": [
                    {
                        "given": "John",
                        "family": "Jumper",
                        "affiliation": [{"name": "DeepMind"}],
                    },
                    {
                        "given": "Richard",
                        "family": "Evans",
                        "affiliation": [],
                    },
                ],
                "abstract": "<jats:p>We present AlphaFold, an AI system.</jats:p>",
                "published-print": {"date-parts": [[2021, 7, 15]]},
                "container-title": ["Nature"],
                "is-referenced-by-count": 15000,
                "type": "journal-article",
                "ISSN": ["0028-0836"],
                "publisher": "Springer Nature",
                "subject": ["General"],
                "link": [
                    {
                        "URL": "https://example.com/paper.pdf",
                        "content-type": "application/pdf",
                    }
                ],
            }
        ],
    },
}

CROSSREF_SINGLE_WORK = CROSSREF_SEARCH_RESPONSE["message"]["items"][0]


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


async def test_search_basic(httpx_mock: HTTPXMock):
    """search() 正确解析 JSON 并映射字段"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works\?.*"),
        json=CROSSREF_SEARCH_RESPONSE,
    )

    async with CrossrefClient(mailto="test@test.com") as c:
        resp = await c.search("alphafold protein")

    assert resp.source == SourceType.CROSSREF
    assert resp.total_results == 42
    assert resp.page == 1
    assert len(resp.results) == 1

    paper = resp.results[0]
    assert paper.title == "Highly accurate protein structure prediction"
    assert paper.doi == "10.1038/s41586-021-03819-2"
    assert paper.year == 2021
    assert paper.publication_date == date(2021, 7, 15)
    assert paper.citation_count == 15000
    assert paper.journal == "Nature"
    assert paper.source_url == "https://doi.org/10.1038/s41586-021-03819-2"
    assert paper.pdf_url == "https://example.com/paper.pdf"
    assert paper.source == SourceType.CROSSREF


async def test_search_authors(httpx_mock: HTTPXMock):
    """作者及机构正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works.*"),
        json=CROSSREF_SEARCH_RESPONSE,
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    paper = resp.results[0]
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "John Jumper"
    assert paper.authors[0].affiliation == "DeepMind"
    assert paper.authors[1].name == "Richard Evans"
    assert paper.authors[1].affiliation is None


async def test_search_abstract_jats_cleanup(httpx_mock: HTTPXMock):
    """JATS XML 标签被清除"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works.*"),
        json=CROSSREF_SEARCH_RESPONSE,
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    assert resp.results[0].abstract == "We present AlphaFold, an AI system."


async def test_search_empty_results(httpx_mock: HTTPXMock):
    """空结果集正确返回"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works.*"),
        json={"status": "ok", "message": {"total-results": 0, "items": []}},
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        resp = await c.search("nonexistent_xyz_query")

    assert resp.total_results == 0
    assert resp.results == []


async def test_search_raw_fields(httpx_mock: HTTPXMock):
    """raw 字段包含 type, publisher, subject 等"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works.*"),
        json=CROSSREF_SEARCH_RESPONSE,
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    raw = resp.results[0].raw
    assert raw["type"] == "journal-article"
    assert raw["publisher"] == "Springer Nature"
    assert raw["issn"] == ["0028-0836"]


async def test_search_pagination(httpx_mock: HTTPXMock):
    """分页参数正确计算 page"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works.*"),
        json=CROSSREF_SEARCH_RESPONSE,
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        resp = await c.search("test", rows=10, offset=20)

    assert resp.page == 3  # (20 // 10) + 1


# ---------------------------------------------------------------------------
# Date parsing edge cases
# ---------------------------------------------------------------------------


async def test_date_partial_yy_mm(httpx_mock: HTTPXMock):
    """只有年+月时不应让整个结果解析失败。"""
    item = {
        **CROSSREF_SINGLE_WORK,
        "published-print": {"date-parts": [[2022, 3]]},
    }
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works.*"),
        json={"status": "ok", "message": {"total-results": 1, "items": [item]}},
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    assert len(resp.results) == 1
    assert resp.results[0].year == 2022
    assert resp.results[0].publication_date is None
    assert resp.results[0].raw["publication_date_raw"] == "2022-03"
    assert resp.results[0].raw["publication_date_precision"] == "month"


async def test_date_fallback_to_online(httpx_mock: HTTPXMock):
    """published-print 缺失时 fallback 到 published-online"""
    item = dict(CROSSREF_SINGLE_WORK)
    del item["published-print"]
    item["published-online"] = {"date-parts": [[2020, 11, 5]]}
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works.*"),
        json={"status": "ok", "message": {"total-results": 1, "items": [item]}},
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    assert resp.results[0].year == 2020
    assert resp.results[0].publication_date == date(2020, 11, 5)


# ---------------------------------------------------------------------------
# get_by_doi
# ---------------------------------------------------------------------------


async def test_get_by_doi(httpx_mock: HTTPXMock):
    """get_by_doi 正确请求并解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works/10\.1038.*"),
        json={"status": "ok", "message": CROSSREF_SINGLE_WORK},
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        paper = await c.get_by_doi("10.1038/s41586-021-03819-2")

    assert paper.title == "Highly accurate protein structure prediction"


async def test_get_by_doi_not_found(httpx_mock: HTTPXMock):
    """不存在的 DOI 抛出 NotFoundError"""
    from souwen.exceptions import NotFoundError

    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works/.*"),
        status_code=404,
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        with pytest.raises(NotFoundError):
            await c.get_by_doi("10.9999/nonexistent")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_missing_optional_fields(httpx_mock: HTTPXMock):
    """缺少可选字段时不抛出异常"""
    minimal_item = {
        "DOI": "10.1234/minimal",
        "title": ["Minimal"],
        "author": [],
        "container-title": [],
        "is-referenced-by-count": 0,
        "type": "journal-article",
        "link": [],
    }
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works.*"),
        json={"status": "ok", "message": {"total-results": 1, "items": [minimal_item]}},
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        resp = await c.search("minimal")

    paper = resp.results[0]
    assert paper.title == "Minimal"
    assert paper.authors == []
    assert paper.abstract == ""
    assert paper.pdf_url is None
    assert paper.year is None


async def test_no_pdf_link(httpx_mock: HTTPXMock):
    """无 PDF 链接时 pdf_url 为 None"""
    item = {**CROSSREF_SINGLE_WORK, "link": []}
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works.*"),
        json={"status": "ok", "message": {"total-results": 1, "items": [item]}},
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    assert resp.results[0].pdf_url is None


async def test_search_skips_malformed_items(httpx_mock: HTTPXMock):
    """单条脏数据不应导致整个 Crossref 源失败。"""
    malformed_item = {
        **CROSSREF_SINGLE_WORK,
        "DOI": "10.1234/bad",
        "author": "not-a-list",
    }
    httpx_mock.add_response(
        url=re.compile(r"https://api\.crossref\.org/works.*"),
        json={
            "status": "ok",
            "message": {
                "total-results": 2,
                "items": [malformed_item, CROSSREF_SINGLE_WORK],
            },
        },
    )

    async with CrossrefClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    assert len(resp.results) == 1
    assert resp.results[0].doi == CROSSREF_SINGLE_WORK["DOI"]
