"""PatentsView API 客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.patent.patentsview`` 中 PatentsViewClient 的 JSON 解析、字段映射、分页、错误处理。
验证申请人/发明人提取、分类代码（CPC/IPC）、摘要、日期处理等不变量。

测试清单：
- ``test_search_basic``：基本搜索解析
- ``test_search_applicants``：申请人提取
- ``test_search_inventors``：发明人提取
- ``test_search_classification_codes``：分类代码（CPC/IPC）
- ``test_search_abstract``：摘要提取
- ``test_search_empty_results``：无结果处理
- ``test_get_patent``：单篇专利查询
- ``test_get_patent_not_found``：专利不存在
- ``test_assignee_fallback_to_person_name``：申请人名称回退
- ``test_invalid_date``：日期格式处理
"""

from __future__ import annotations
import re

import pytest
from datetime import date
from pytest_httpx import HTTPXMock

from souwen.patent.patentsview import PatentsViewClient
from souwen.models import SourceType


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

PATENTSVIEW_SEARCH_RESPONSE = {
    "patents": [
        {
            "patent_id": "11234567",
            "patent_title": "Neural Network Architecture for Image Recognition",
            "patent_abstract": "A method and system for image recognition using deep neural networks with attention mechanisms.",
            "patent_date": "2023-01-31",
            "patent_num_claims": 20,
            "patent_type": "utility",
            "application_number": "US17/123456",
            "application_filing_date": "2021-06-15",
            "assignees": [
                {
                    "assignee_organization": "DeepMind Technologies",
                    "assignee_first_name": None,
                    "assignee_last_name": None,
                    "assignee_country": "GB",
                },
            ],
            "inventors": [
                {
                    "inventor_first_name": "John",
                    "inventor_last_name": "Smith",
                },
                {
                    "inventor_first_name": "Jane",
                    "inventor_last_name": "Doe",
                },
            ],
            "cpcs": [
                {"cpc_group_id": "G06N3/08"},
                {"cpc_group_id": "G06V10/82"},
            ],
            "ipcs": [
                {"ipc_group": "G06N3/00"},
            ],
        }
    ],
    "total_patent_count": 150,
}


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


async def test_search_basic(httpx_mock: HTTPXMock):
    """search() 正确解析 JSON 并映射字段。"""
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=PATENTSVIEW_SEARCH_RESPONSE,
    )

    async with PatentsViewClient() as c:
        resp = await c.search({"_contains": {"patent_title": "neural network"}})

    assert resp.source == SourceType.PATENTSVIEW
    assert resp.total_results == 150
    assert resp.page == 1
    assert len(resp.results) == 1

    patent = resp.results[0]
    assert patent.title == "Neural Network Architecture for Image Recognition"
    assert patent.patent_id == "11234567"
    assert patent.application_number == "US17/123456"
    assert patent.publication_date == date(2023, 1, 31)
    assert patent.filing_date == date(2021, 6, 15)
    assert patent.source == SourceType.PATENTSVIEW
    assert patent.source_url == "https://search.patentsview.org/patent/11234567"


async def test_search_applicants(httpx_mock: HTTPXMock):
    """受让人（applicants）正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=PATENTSVIEW_SEARCH_RESPONSE,
    )

    async with PatentsViewClient() as c:
        resp = await c.search({"_contains": {"patent_title": "test"}})

    patent = resp.results[0]
    assert len(patent.applicants) == 1
    assert patent.applicants[0].name == "DeepMind Technologies"
    assert patent.applicants[0].country == "GB"


async def test_search_inventors(httpx_mock: HTTPXMock):
    """发明人正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=PATENTSVIEW_SEARCH_RESPONSE,
    )

    async with PatentsViewClient() as c:
        resp = await c.search({"_contains": {"patent_title": "test"}})

    patent = resp.results[0]
    assert len(patent.inventors) == 2
    assert patent.inventors[0] == "John Smith"
    assert patent.inventors[1] == "Jane Doe"


async def test_search_classification_codes(httpx_mock: HTTPXMock):
    """CPC/IPC 分类号正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=PATENTSVIEW_SEARCH_RESPONSE,
    )

    async with PatentsViewClient() as c:
        resp = await c.search({"_contains": {"patent_title": "test"}})

    patent = resp.results[0]
    assert patent.cpc_codes == ["G06N3/08", "G06V10/82"]
    assert patent.ipc_codes == ["G06N3/00"]


async def test_search_abstract(httpx_mock: HTTPXMock):
    """摘要正确映射"""
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=PATENTSVIEW_SEARCH_RESPONSE,
    )

    async with PatentsViewClient() as c:
        resp = await c.search({"_contains": {"patent_title": "test"}})

    assert "attention mechanisms" in resp.results[0].abstract


async def test_search_empty_results(httpx_mock: HTTPXMock):
    """空结果集正确返回"""
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json={"patents": [], "total_patent_count": 0},
    )

    async with PatentsViewClient() as c:
        resp = await c.search({"_contains": {"patent_title": "xyz_nonexistent"}})

    assert resp.total_results == 0
    assert resp.results == []


# ---------------------------------------------------------------------------
# get_patent
# ---------------------------------------------------------------------------


async def test_get_patent(httpx_mock: HTTPXMock):
    """get_patent 正确请求并解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=PATENTSVIEW_SEARCH_RESPONSE,
    )

    async with PatentsViewClient() as c:
        patent = await c.get_patent("11234567")

    assert patent.title == "Neural Network Architecture for Image Recognition"
    assert patent.patent_id == "11234567"


async def test_get_patent_not_found(httpx_mock: HTTPXMock):
    """不存在的专利抛出 NotFoundError"""
    from souwen.core.exceptions import NotFoundError

    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json={"patents": [], "total_patent_count": 0},
    )

    async with PatentsViewClient() as c:
        with pytest.raises(NotFoundError):
            await c.get_patent("99999999")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_assignee_fallback_to_person_name(httpx_mock: HTTPXMock):
    """assignee_organization 为空时回退到 first+last name"""
    data = {
        "patents": [
            {
                "patent_id": "99999",
                "patent_title": "Test Patent",
                "patent_abstract": None,
                "patent_date": None,
                "application_number": None,
                "application_filing_date": None,
                "assignees": [
                    {
                        "assignee_organization": None,
                        "assignee_first_name": "Alice",
                        "assignee_last_name": "Wonder",
                        "assignee_country": "US",
                    }
                ],
                "inventors": [],
                "cpcs": [],
                "ipcs": [],
            }
        ],
        "total_patent_count": 1,
    }
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=data,
    )

    async with PatentsViewClient() as c:
        resp = await c.search({"_contains": {"patent_title": "test"}})

    assert resp.results[0].applicants[0].name == "Alice Wonder"


async def test_invalid_date(httpx_mock: HTTPXMock):
    """无效日期字符串不会导致崩溃"""
    data = {
        "patents": [
            {
                "patent_id": "88888",
                "patent_title": "Bad Date Patent",
                "patent_date": "not-a-date",
                "application_filing_date": "",
                "patent_abstract": None,
                "application_number": None,
                "assignees": [],
                "inventors": [],
                "cpcs": [],
                "ipcs": [],
            }
        ],
        "total_patent_count": 1,
    }
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=data,
    )

    async with PatentsViewClient() as c:
        resp = await c.search({"_contains": {"patent_title": "test"}})

    patent = resp.results[0]
    assert patent.publication_date is None
    assert patent.filing_date is None


async def test_null_lists(httpx_mock: HTTPXMock):
    """assignees/inventors/cpcs/ipcs 为 null 时不崩溃"""
    data = {
        "patents": [
            {
                "patent_id": "77777",
                "patent_title": "Null Lists Patent",
                "patent_abstract": None,
                "patent_date": "2023-05-01",
                "application_number": None,
                "application_filing_date": None,
                "assignees": None,
                "inventors": None,
                "cpcs": None,
                "ipcs": None,
            }
        ],
        "total_patent_count": 1,
    }
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=data,
    )

    async with PatentsViewClient() as c:
        resp = await c.search({"_contains": {"patent_title": "test"}})

    patent = resp.results[0]
    assert patent.applicants == []
    assert patent.inventors == []
    assert patent.cpc_codes == []
    assert patent.ipc_codes == []


async def test_search_by_assignee(httpx_mock: HTTPXMock):
    """search_by_assignee 便利方法正确工作"""
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=PATENTSVIEW_SEARCH_RESPONSE,
    )

    async with PatentsViewClient() as c:
        resp = await c.search_by_assignee("DeepMind")

    assert len(resp.results) == 1


async def test_search_by_inventor(httpx_mock: HTTPXMock):
    """search_by_inventor 便利方法正确工作"""
    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        json=PATENTSVIEW_SEARCH_RESPONSE,
    )

    async with PatentsViewClient() as c:
        resp = await c.search_by_inventor("Smith")

    assert len(resp.results) == 1


# ---------------------------------------------------------------------------
# HTTP 错误路径（P0-5）
# ---------------------------------------------------------------------------


async def test_429_raises_rate_limit(httpx_mock: HTTPXMock):
    """429 响应被 http_client 层识别为 RateLimitError 并携带 retry_after"""
    from souwen.core.exceptions import RateLimitError

    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        status_code=429,
        headers={"Retry-After": "30"},
        json={"error": "rate limited"},
    )

    with pytest.raises(RateLimitError) as exc_info:
        async with PatentsViewClient() as c:
            await c.search({"_contains": {"patent_title": "x"}})
    assert exc_info.value.retry_after == 30.0


async def test_401_raises_auth_error(httpx_mock: HTTPXMock):
    """401 响应被识别为 AuthError"""
    from souwen.core.exceptions import AuthError

    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        status_code=401,
        json={"error": "unauthorized"},
    )

    with pytest.raises(AuthError):
        async with PatentsViewClient() as c:
            await c.search({"_contains": {"patent_title": "x"}})


async def test_503_raises_source_unavailable(httpx_mock: HTTPXMock):
    """5xx 响应被识别为 SourceUnavailableError"""
    from souwen.core.exceptions import SourceUnavailableError

    httpx_mock.add_response(
        url=re.compile(r"https://search\.patentsview\.org/api/v1/patent/"),
        status_code=503,
        json={"error": "down"},
    )

    with pytest.raises(SourceUnavailableError):
        async with PatentsViewClient() as c:
            await c.search({"_contains": {"patent_title": "x"}})
