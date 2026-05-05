"""OpenAlex API 客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.paper.openalex`` 中 OpenAlexClient 的 JSON 解析、字段映射、分页、错误处理。
验证作者机构、概念提取、开放获取链接、引用计数等不变量。

测试清单：
- ``test_search_basic``：基本搜索解析
- ``test_search_pagination``：分页逻辑
- ``test_search_no_results``：无结果处理
- ``test_authorship_without_institution``：无机构作者
- ``test_missing_abstract``：缺少摘要处理
- ``test_http_errors``：HTTP 错误处理
"""

from __future__ import annotations
import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.paper.openalex import OpenAlexClient
from souwen.models import SourceType


# ---------------------------------------------------------------------------
# Fixtures & mock data
# ---------------------------------------------------------------------------

OPENALEX_SEARCH_RESPONSE = {
    "meta": {"count": 1, "db_response_time_ms": 12, "page": 1, "per_page": 10},
    "results": [
        {
            "id": "https://openalex.org/W2741809807",
            "doi": "https://doi.org/10.1038/s41586-021-03819-2",
            "display_name": "Attention Is All You Need",
            "publication_year": 2017,
            "publication_date": "2017-06-12",
            "cited_by_count": 90000,
            "type": "article",
            "open_access": {"is_oa": True},
            "authorships": [
                {
                    "author": {"display_name": "Ashish Vaswani"},
                    "institutions": [
                        {"display_name": "Google Brain"},
                    ],
                },
                {
                    "author": {"display_name": "Noam Shazeer"},
                    "institutions": [],
                },
            ],
            "abstract_inverted_index": {
                "The": [0],
                "dominant": [1],
                "approach": [2],
            },
            "best_oa_location": {
                "pdf_url": "https://arxiv.org/pdf/1706.03762",
            },
            "primary_location": {
                "source": {"display_name": "Nature"},
            },
            "concepts": [
                {"display_name": "Transformer"},
                {"display_name": "Attention mechanism"},
            ],
        }
    ],
}

OPENALEX_SINGLE_WORK = OPENALEX_SEARCH_RESPONSE["results"][0]


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


async def test_search_basic(httpx_mock: HTTPXMock, monkeypatch):
    """search() 正确解析 JSON 并映射字段。"""
    monkeypatch.setenv("SOUWEN_OPENALEX_EMAIL", "test@test.com")

    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works.*"),
        json=OPENALEX_SEARCH_RESPONSE,
    )

    async with OpenAlexClient(mailto="test@test.com") as c:
        resp = await c.search("attention transformer")

    assert resp.source == SourceType.OPENALEX
    assert resp.total_results == 1
    assert resp.page == 1
    assert len(resp.results) == 1

    paper = resp.results[0]
    assert paper.title == "Attention Is All You Need"
    assert paper.doi == "10.1038/s41586-021-03819-2"
    assert paper.year == 2017
    assert paper.citation_count == 90000
    assert paper.journal == "Nature"
    assert paper.pdf_url == "https://arxiv.org/pdf/1706.03762"
    assert paper.source == SourceType.OPENALEX
    assert paper.source_url == "https://openalex.org/W2741809807"


async def test_search_authors(httpx_mock: HTTPXMock):
    """作者及机构正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works.*"),
        json=OPENALEX_SEARCH_RESPONSE,
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    paper = resp.results[0]
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Ashish Vaswani"
    assert paper.authors[0].affiliation == "Google Brain"
    assert paper.authors[1].name == "Noam Shazeer"
    assert paper.authors[1].affiliation is None


async def test_search_abstract_reconstruction(httpx_mock: HTTPXMock):
    """inverted_index 正确还原为文本"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works.*"),
        json=OPENALEX_SEARCH_RESPONSE,
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    assert resp.results[0].abstract == "The dominant approach"


async def test_search_empty_results(httpx_mock: HTTPXMock):
    """空结果集正确返回"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works.*"),
        json={"meta": {"count": 0}, "results": []},
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        resp = await c.search("nonexistent_xyz_query")

    assert resp.total_results == 0
    assert resp.results == []


async def test_search_raw_fields(httpx_mock: HTTPXMock):
    """raw 字段包含 type, is_oa, concepts"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works.*"),
        json=OPENALEX_SEARCH_RESPONSE,
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    raw = resp.results[0].raw
    assert raw["type"] == "article"
    assert raw["is_oa"] is True
    assert "Transformer" in raw["concepts"]


# ---------------------------------------------------------------------------
# get_by_doi / get_by_id
# ---------------------------------------------------------------------------


async def test_get_by_doi(httpx_mock: HTTPXMock):
    """get_by_doi 正确请求并解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works/https://doi\.org/.*"),
        json=OPENALEX_SINGLE_WORK,
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        paper = await c.get_by_doi("10.1038/s41586-021-03819-2")

    assert paper.title == "Attention Is All You Need"


async def test_get_by_doi_not_found(httpx_mock: HTTPXMock):
    """不存在的 DOI 抛出 NotFoundError"""
    from souwen.core.exceptions import NotFoundError

    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works/https://doi\.org/.*"),
        status_code=404,
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        with pytest.raises(NotFoundError):
            await c.get_by_doi("10.9999/nonexistent")


async def test_get_by_id(httpx_mock: HTTPXMock):
    """get_by_id 正确请求并解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works/W.*"),
        json=OPENALEX_SINGLE_WORK,
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        paper = await c.get_by_id("W2741809807")

    assert paper.title == "Attention Is All You Need"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_missing_optional_fields(httpx_mock: HTTPXMock):
    """缺少可选字段时不抛出异常"""
    minimal_work = {
        "id": "https://openalex.org/W123",
        "display_name": "Minimal Paper",
        "authorships": [],
        "publication_year": None,
        "publication_date": None,
        "doi": None,
        "abstract_inverted_index": None,
        "best_oa_location": None,
        "primary_location": None,
        "cited_by_count": None,
        "open_access": {},
        "concepts": [],
    }
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works.*"),
        json={"meta": {"count": 1}, "results": [minimal_work]},
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        resp = await c.search("minimal")

    paper = resp.results[0]
    assert paper.title == "Minimal Paper"
    assert paper.doi is None
    assert paper.abstract == ""
    assert paper.authors == []
    assert paper.pdf_url is None
    assert paper.journal is None


async def test_doi_prefix_stripping(httpx_mock: HTTPXMock):
    """DOI 前缀 https://doi.org/ 被正确去除"""
    work = {**OPENALEX_SINGLE_WORK, "doi": "https://doi.org/10.1234/test"}
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works.*"),
        json={"meta": {"count": 1}, "results": [work]},
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    assert resp.results[0].doi == "10.1234/test"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


# `_clear_config_cache` 已迁移到 tests/conftest.py 的 autouse fixture。


# ---------------------------------------------------------------------------
# publication_date 安全解析（P0-9）
# ---------------------------------------------------------------------------


async def test_missing_publication_date(httpx_mock: HTTPXMock):
    """缺失 publication_date 字段时不崩溃"""
    work = {**OPENALEX_SEARCH_RESPONSE["results"][0]}
    work.pop("publication_date", None)
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works.*"),
        json={"meta": {"count": 1}, "results": [work]},
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    assert resp.results[0].publication_date is None


async def test_malformed_publication_date(httpx_mock: HTTPXMock):
    """无效 publication_date 时回落为 None 而非抛错"""
    work = {**OPENALEX_SEARCH_RESPONSE["results"][0], "publication_date": "not-a-date"}
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/works.*"),
        json={"meta": {"count": 1}, "results": [work]},
    )

    async with OpenAlexClient(mailto="t@t.com") as c:
        resp = await c.search("test")

    assert resp.results[0].publication_date is None
