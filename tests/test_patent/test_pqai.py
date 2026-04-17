"""PQAI 语义专利检索客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.patent.pqai`` 中 PqaiClient 的 JSON 解析、字段映射、申请人/发明人格式兼容性。
验证混合申请人/发明人格式（字符串/字典）、CPC 代码、相似专利查询、CPC 预测等不变量。

测试清单：
- ``test_search_basic``：基本搜索解析
- ``test_search_string_assignees``：字符串格式申请人
- ``test_search_dict_assignees``：字典格式申请人
- ``test_search_string_inventors``：字符串格式发明人
- ``test_search_dict_inventors``：字典格式发明人
- ``test_search_cpc_codes_both_keys``：CPC 代码（多字段兼容）
- ``test_search_empty_results``：无结果处理
- ``test_similar_patents``：相似专利查询
- ``test_similar_patents_not_found``：相似专利不存在
- ``test_predict_cpc``：CPC 分类预测
"""

from __future__ import annotations
import re

import pytest
from datetime import date
from pytest_httpx import HTTPXMock

from souwen.patent.pqai import PqaiClient
from souwen.models import SourceType


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

PQAI_SEARCH_RESPONSE = {
    "results": [
        {
            "id": "US11234567B2",
            "title": "Machine Learning Method for Cancer Detection",
            "abstract": "A method for detecting cancer using machine learning on MRI images with improved accuracy.",
            "publication_date": "2023-03-14",
            "assignees": ["Google LLC", "DeepMind Technologies"],
            "inventors": ["Alice Johnson", "Bob Williams"],
            "cpcs": ["A61B5/7267", "G06N3/08"],
        },
        {
            "id": "US10987654B1",
            "title": "Deep Learning Image Analysis",
            "abstract": "System for analyzing medical images using deep learning techniques.",
            "publication_date": "2022-11-01",
            "assignees": [
                {"name": "Microsoft Corp", "country": "US"},
            ],
            "inventors": [
                {"name": "Charlie Brown"},
            ],
            "cpc_codes": ["G06T7/00"],
        },
    ],
}


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


async def test_search_basic(httpx_mock: HTTPXMock):
    """search() 正确解析 JSON 并映射字段。"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json=PQAI_SEARCH_RESPONSE,
    )

    async with PqaiClient() as c:
        resp = await c.search("cancer detection machine learning")

    assert resp.source == SourceType.PQAI
    assert resp.total_results == 2
    assert resp.page == 1
    assert len(resp.results) == 2

    patent = resp.results[0]
    assert patent.title == "Machine Learning Method for Cancer Detection"
    assert patent.patent_id == "US11234567B2"
    assert patent.publication_date == date(2023, 3, 14)
    assert patent.source == SourceType.PQAI
    assert patent.source_url == "https://patents.google.com/patent/US11234567B2"
    assert "machine learning" in patent.abstract.lower()


async def test_search_string_assignees(httpx_mock: HTTPXMock):
    """字符串格式的 assignees 正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json=PQAI_SEARCH_RESPONSE,
    )

    async with PqaiClient() as c:
        resp = await c.search("test")

    patent = resp.results[0]
    assert len(patent.applicants) == 2
    assert patent.applicants[0].name == "Google LLC"
    assert patent.applicants[0].country is None
    assert patent.applicants[1].name == "DeepMind Technologies"


async def test_search_dict_assignees(httpx_mock: HTTPXMock):
    """字典格式的 assignees 正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json=PQAI_SEARCH_RESPONSE,
    )

    async with PqaiClient() as c:
        resp = await c.search("test")

    patent = resp.results[1]
    assert len(patent.applicants) == 1
    assert patent.applicants[0].name == "Microsoft Corp"
    assert patent.applicants[0].country == "US"


async def test_search_string_inventors(httpx_mock: HTTPXMock):
    """字符串格式的 inventors 正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json=PQAI_SEARCH_RESPONSE,
    )

    async with PqaiClient() as c:
        resp = await c.search("test")

    patent = resp.results[0]
    assert patent.inventors == ["Alice Johnson", "Bob Williams"]


async def test_search_dict_inventors(httpx_mock: HTTPXMock):
    """字典格式的 inventors 正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json=PQAI_SEARCH_RESPONSE,
    )

    async with PqaiClient() as c:
        resp = await c.search("test")

    patent = resp.results[1]
    assert patent.inventors == ["Charlie Brown"]


async def test_search_cpc_codes_both_keys(httpx_mock: HTTPXMock):
    """cpcs 和 cpc_codes 两种 key 都能正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json=PQAI_SEARCH_RESPONSE,
    )

    async with PqaiClient() as c:
        resp = await c.search("test")

    # First result uses "cpcs" key
    assert resp.results[0].cpc_codes == ["A61B5/7267", "G06N3/08"]
    # Second result uses "cpc_codes" key
    assert resp.results[1].cpc_codes == ["G06T7/00"]


async def test_search_empty_results(httpx_mock: HTTPXMock):
    """空结果集正确返回"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json={"results": []},
    )

    async with PqaiClient() as c:
        resp = await c.search("nonexistent_xyz_query")

    assert resp.total_results == 0
    assert resp.results == []


# ---------------------------------------------------------------------------
# similar_patents
# ---------------------------------------------------------------------------


async def test_similar_patents(httpx_mock: HTTPXMock):
    """similar_patents 正确请求并解析"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/similar/US11234567B2.*"),
        json=PQAI_SEARCH_RESPONSE,
    )

    async with PqaiClient() as c:
        resp = await c.similar_patents("US11234567B2")

    assert len(resp.results) == 2
    assert resp.query == "similar:US11234567B2"


async def test_similar_patents_not_found(httpx_mock: HTTPXMock):
    """不存在的专利 ID 抛出 NotFoundError"""
    from souwen.exceptions import NotFoundError

    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/similar/.*"),
        status_code=404,
    )

    async with PqaiClient() as c:
        with pytest.raises(NotFoundError):
            await c.similar_patents("NONEXISTENT")


# ---------------------------------------------------------------------------
# predict_cpc
# ---------------------------------------------------------------------------


async def test_predict_cpc(httpx_mock: HTTPXMock):
    """predict_cpc 正确请求并返回预测列表"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/classify/cpc.*"),
        json={
            "predictions": [
                {"code": "G06N3/08", "score": 0.95},
                {"code": "G06V10/82", "score": 0.72},
            ]
        },
    )

    async with PqaiClient() as c:
        predictions = await c.predict_cpc("neural network for image recognition")

    assert len(predictions) == 2
    assert predictions[0]["code"] == "G06N3/08"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_publication_number_fallback(httpx_mock: HTTPXMock):
    """id 缺失时回退到 publication_number"""
    data = {
        "results": [
            {
                "publication_number": "EP1234567A1",
                "title": "European Patent",
                "abstract": "An abstract.",
                "publication_date": "2022-01-01",
                "assignees": [],
                "inventors": [],
            }
        ],
    }
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json=data,
    )

    async with PqaiClient() as c:
        resp = await c.search("test")

    assert resp.results[0].patent_id == "EP1234567A1"


async def test_invalid_publication_date(httpx_mock: HTTPXMock):
    """无效日期字符串不崩溃"""
    data = {
        "results": [
            {
                "id": "US999",
                "title": "Bad Date",
                "abstract": None,
                "publication_date": "invalid-date",
                "assignees": [],
                "inventors": [],
            }
        ],
    }
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json=data,
    )

    async with PqaiClient() as c:
        resp = await c.search("test")

    assert resp.results[0].publication_date is None


async def test_missing_all_optional_fields(httpx_mock: HTTPXMock):
    """所有可选字段缺失时不崩溃"""
    data = {
        "results": [
            {
                "id": "US000",
                "title": "Minimal Patent",
            }
        ],
    }
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json=data,
    )

    async with PqaiClient() as c:
        resp = await c.search("test")

    patent = resp.results[0]
    assert patent.title == "Minimal Patent"
    assert patent.applicants == []
    assert patent.inventors == []
    assert patent.cpc_codes == []
    assert patent.abstract is None
    assert patent.publication_date is None


async def test_cpc_dict_format(httpx_mock: HTTPXMock):
    """CPC 为字典格式时正确解析"""
    data = {
        "results": [
            {
                "id": "US555",
                "title": "Dict CPC",
                "cpcs": [
                    {"code": "H04L9/32"},
                    {"code": "G06F21/00"},
                ],
            }
        ],
    }
    httpx_mock.add_response(
        url=re.compile(r"https://api\.projectpq\.ai/search/102.*"),
        json=data,
    )

    async with PqaiClient() as c:
        resp = await c.search("test")

    assert resp.results[0].cpc_codes == ["H04L9/32", "G06F21/00"]
