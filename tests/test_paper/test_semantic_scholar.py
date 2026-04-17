"""Semantic Scholar API 客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.paper.semantic_scholar`` 中 SemanticScholarClient 的 JSON 解析、
字段映射、HTTP 错误处理。验证 P0-4 中 HTTP 错误分支（429/401/5xx）在进入 
``.json()`` 解析前抛出明确异常，字段映射完整性等不变量。

测试清单：
- ``test_search_basic``：基本搜索解析
- ``test_search_pagination``：分页
- ``test_search_no_results``：无结果
- ``test_missing_doi``：缺少 DOI
- ``test_http_429_raises_ratelimiterror``：429 限流错误
- ``test_http_401_raises_autherror``：401 认证错误
- ``test_http_5xx_raises_unavailable``：5xx 服务错误
"""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.models import SourceType
from souwen.paper.semantic_scholar import SemanticScholarClient


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

S2_SEARCH_RESPONSE = {
    "total": 1,
    "data": [
        {
            "paperId": "abc123",
            "externalIds": {"DOI": "10.1000/xyz"},
            "title": "Attention Is All You Need",
            "abstract": "We propose a new architecture...",
            "year": 2017,
            "publicationDate": "2017-06-12",
            "authors": [{"name": "Ashish Vaswani"}],
            "citationCount": 10000,
            "referenceCount": 30,
            "isOpenAccess": True,
            "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762"},
            "venue": "NeurIPS",
            "tldr": {"text": "Transformers."},
        }
    ],
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_search_basic(httpx_mock: HTTPXMock):
    """搜索成功解析 JSON 并映射字段"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.semanticscholar\.org/graph/v1/paper/search.*"),
        json=S2_SEARCH_RESPONSE,
    )

    async with SemanticScholarClient(api_key=None) as c:
        resp = await c.search("transformer")

    assert resp.source == SourceType.SEMANTIC_SCHOLAR
    assert resp.total_results == 1
    paper = resp.results[0]
    assert paper.title == "Attention Is All You Need"
    assert paper.doi == "10.1000/xyz"
    assert paper.tldr == "Transformers."


async def test_search_missing_publication_date(httpx_mock: HTTPXMock):
    """缺失 publicationDate 时不抛异常（safe_parse_date 容错）"""
    payload = {
        "total": 1,
        "data": [
            {
                "paperId": "p1",
                "externalIds": {},
                "title": "No date paper",
                "abstract": "",
                "year": None,
                "publicationDate": None,
                "authors": [],
                "citationCount": None,
            }
        ],
    }
    httpx_mock.add_response(
        url=re.compile(r"https://api\.semanticscholar\.org/graph/v1/paper/search.*"),
        json=payload,
    )

    async with SemanticScholarClient(api_key=None) as c:
        resp = await c.search("x")
    assert resp.results[0].publication_date is None


# ---------------------------------------------------------------------------
# HTTP 错误分支（P0-4）
# ---------------------------------------------------------------------------


async def test_search_rate_limit_raises(httpx_mock: HTTPXMock):
    """429 响应抛 RateLimitError，且携带 Retry-After。"""
    from souwen.exceptions import RateLimitError

    httpx_mock.add_response(
        url=re.compile(r"https://api\.semanticscholar\.org/graph/v1/paper/search.*"),
        status_code=429,
        headers={"Retry-After": "60"},
        text="rate limited",
    )

    async with SemanticScholarClient(api_key=None) as c:
        with pytest.raises(RateLimitError) as ei:
            await c.search("x")
    assert ei.value.retry_after == 60


async def test_search_auth_error(httpx_mock: HTTPXMock):
    """401 响应抛 AuthError。"""
    from souwen.exceptions import AuthError

    httpx_mock.add_response(
        url=re.compile(r"https://api\.semanticscholar\.org/graph/v1/paper/search.*"),
        status_code=401,
        text="unauthorized",
    )

    async with SemanticScholarClient(api_key=None) as c:
        with pytest.raises(AuthError):
            await c.search("x")


async def test_search_forbidden_is_auth_error(httpx_mock: HTTPXMock):
    """403 响应也归类为 AuthError。"""
    from souwen.exceptions import AuthError

    httpx_mock.add_response(
        url=re.compile(r"https://api\.semanticscholar\.org/graph/v1/paper/search.*"),
        status_code=403,
    )

    async with SemanticScholarClient(api_key=None) as c:
        with pytest.raises(AuthError):
            await c.search("x")


async def test_search_server_error(httpx_mock: HTTPXMock):
    """5xx 响应抛 SourceUnavailableError，不走 .json()。"""
    from souwen.exceptions import SourceUnavailableError

    httpx_mock.add_response(
        url=re.compile(r"https://api\.semanticscholar\.org/graph/v1/paper/search.*"),
        status_code=502,
        text="bad gateway",
    )

    async with SemanticScholarClient(api_key=None) as c:
        with pytest.raises(SourceUnavailableError):
            await c.search("x")


async def test_get_paper_rate_limit(httpx_mock: HTTPXMock):
    """get_paper 同样遵循统一错误分支。"""
    from souwen.exceptions import RateLimitError

    httpx_mock.add_response(
        url=re.compile(r"https://api\.semanticscholar\.org/graph/v1/paper/.*"),
        status_code=429,
        headers={"Retry-After": "10"},
    )

    async with SemanticScholarClient(api_key=None) as c:
        with pytest.raises(RateLimitError):
            await c.get_paper("abc")
