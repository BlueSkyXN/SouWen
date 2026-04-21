"""arXiv API 客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.paper.arxiv`` 中 ArxivClient 的搜索解析、字段映射、错误处理。
验证 Atom XML 解析、作者/摘要提取、分页、无 DOI 处理、API 错误场景等不变量。

测试清单：
- ``test_search_basic``：基本搜索解析
- ``test_search_authors``：作者与机构提取
- ``test_search_abstract_whitespace``：摘要空白处理
- ``test_search_raw_fields``：原始字段
- ``test_search_empty_results``：空结果
- ``test_no_doi``：无 DOI 处理
- ``test_malformed_xml``：格式错误的 XML
- ``test_id_list_search``：ID 列表搜索
- ``test_pagination``：分页
"""

from __future__ import annotations
import re
from datetime import date

import pytest
from pytest_httpx import HTTPXMock

from souwen.paper.arxiv import ArxivClient
from souwen.models import SourceType


# ---------------------------------------------------------------------------
# Mock XML data
# ---------------------------------------------------------------------------

ARXIV_SEARCH_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>10</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <summary>The dominant sequence transduction models are based on complex
recurrent or convolutional neural networks.</summary>
    <published>2017-06-12T17:57:34Z</published>
    <updated>2023-08-02T00:41:18Z</updated>
    <author>
      <name>Ashish Vaswani</name>
      <arxiv:affiliation>Google Brain</arxiv:affiliation>
    </author>
    <author>
      <name>Noam Shazeer</name>
    </author>
    <link href="http://arxiv.org/abs/1706.03762v7" rel="alternate" type="text/html"/>
    <link href="http://arxiv.org/pdf/1706.03762v7" rel="related" type="application/pdf"
          title="pdf"/>
    <arxiv:doi>10.48550/arXiv.1706.03762</arxiv:doi>
    <category term="cs.CL"/>
    <category term="cs.AI"/>
    <arxiv:comment>15 pages, 5 figures</arxiv:comment>
  </entry>
</feed>
"""

ARXIV_EMPTY_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>0</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>10</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/api/errors#1</id>
    <title>Error</title>
    <summary>No results found</summary>
  </entry>
</feed>
"""

ARXIV_NO_DOI_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>A Simple Paper</title>
    <summary>Short abstract.</summary>
    <published>2023-01-01T00:00:00Z</published>
    <author>
      <name>Alice Smith</name>
    </author>
    <link href="http://arxiv.org/abs/2301.00001v1" rel="alternate" type="text/html"/>
    <category term="cs.LG"/>
  </entry>
</feed>
"""


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


async def test_search_basic(httpx_mock: HTTPXMock):
    """search() 正确解析 Atom XML 并映射字段。"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_SEARCH_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("attention transformer")

    assert resp.source == SourceType.ARXIV
    assert resp.total_results == 1
    assert resp.page == 1
    assert len(resp.results) == 1

    paper = resp.results[0]
    assert paper.title == "Attention Is All You Need"
    assert paper.doi == "10.48550/arXiv.1706.03762"
    assert paper.year == 2017
    assert paper.publication_date == date(2017, 6, 12)
    assert paper.citation_count is None  # arXiv 不提供引用数
    assert paper.source == SourceType.ARXIV
    assert paper.source_url == "http://arxiv.org/abs/1706.03762v7"
    assert "1706.03762" in paper.pdf_url


async def test_search_authors(httpx_mock: HTTPXMock):
    """作者及机构正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_SEARCH_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("test")

    paper = resp.results[0]
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Ashish Vaswani"
    assert paper.authors[0].affiliation == "Google Brain"
    assert paper.authors[1].name == "Noam Shazeer"
    assert paper.authors[1].affiliation is None


async def test_search_abstract_whitespace(httpx_mock: HTTPXMock):
    """多行 summary 的空白正确合并"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_SEARCH_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("test")

    abstract = resp.results[0].abstract
    # 换行被合并为空格
    assert "\n" not in abstract
    assert "complex recurrent" in abstract


async def test_search_raw_fields(httpx_mock: HTTPXMock):
    """raw 字段包含 categories, primary_category, comment"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_SEARCH_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("test")

    raw = resp.results[0].raw
    assert raw["categories"] == ["cs.CL", "cs.AI"]
    assert raw["primary_category"] == "cs.CL"
    assert raw["comment"] == "15 pages, 5 figures"


async def test_search_empty_results(httpx_mock: HTTPXMock):
    """空结果集（arXiv 的 Error entry）正确处理"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_EMPTY_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("nonexistent_xyz_query")

    assert resp.total_results == 0
    assert resp.results == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_no_doi(httpx_mock: HTTPXMock):
    """无 DOI 的论文正确解析"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_NO_DOI_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("test")

    paper = resp.results[0]
    assert paper.doi is None
    assert paper.title == "A Simple Paper"
    assert paper.year == 2023
    # fallback PDF URL
    assert paper.pdf_url == "https://arxiv.org/pdf/2301.00001v1"


async def test_malformed_xml(httpx_mock: HTTPXMock):
    """无效 XML 抛出 ParseError"""
    from souwen.exceptions import ParseError

    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text="<not valid xml",
    )

    async with ArxivClient() as c:
        with pytest.raises(ParseError):
            await c.search("test")


async def test_id_list_search(httpx_mock: HTTPXMock):
    """id_list 参数正确传递"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_SEARCH_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("", id_list=["1706.03762"])

    assert len(resp.results) == 1


async def test_pagination(httpx_mock: HTTPXMock):
    """分页参数正确计算 page"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_SEARCH_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("test", start=20, max_results=10)

    assert resp.page == 3  # (20 // 10) + 1


# ---------------------------------------------------------------------------
# Categories & date range filtering (Feature 1)
# ---------------------------------------------------------------------------


def test_build_search_query_categories_only():
    """仅给定 categories 时，将 ``OR`` 拼接的分类子句 ``AND`` 到原 query。"""
    q = ArxivClient._build_search_query("transformer", categories=["cs.AI", "cs.LG"])
    assert q == "(transformer) AND (cat:cs.AI OR cat:cs.LG)"


def test_build_search_query_date_range():
    """日期范围使用 ``+TO+`` 字面 ``+`` 字符。"""
    q = ArxivClient._build_search_query("transformer", date_from="2024-01-01", date_to="2024-06-30")
    assert "submittedDate:[202401010000+TO+202406302359]" in q
    assert "(transformer) AND" in q


def test_build_search_query_partial_date():
    """缺省 date_to 时使用极大值占位。"""
    q = ArxivClient._build_search_query("", date_from="2024-01-01")
    assert "202401010000+TO+999912312359" in q


async def test_search_with_categories(httpx_mock: HTTPXMock):
    """search() categories 参数正确拼到 search_query。"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_SEARCH_XML,
    )

    async with ArxivClient() as c:
        await c.search("attention", categories=["cs.AI", "cs.LG"])

    request = httpx_mock.get_requests()[0]
    # 注意 httpx 会将空格编码为 + 或 %20，我们检查关键子串
    url_str = str(request.url)
    assert "cat:cs.AI" in url_str or "cat%3Acs.AI" in url_str
    assert "cat:cs.LG" in url_str or "cat%3Acs.LG" in url_str


async def test_search_with_date_range_preserves_plus_to_plus(httpx_mock: HTTPXMock):
    """search() date_from/date_to 拼到 URL 时，``+TO+`` 不被编码为 ``%2BTO%2B``。"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_SEARCH_XML,
    )

    async with ArxivClient() as c:
        await c.search(
            "attention",
            date_from="2024-01-01",
            date_to="2024-06-30",
        )

    request = httpx_mock.get_requests()[0]
    raw_url = str(request.url)
    # 关键不变量：字面 ``+TO+`` 必须保留
    assert "+TO+" in raw_url
    assert "%2BTO%2B" not in raw_url
    assert "submittedDate:[202401010000+TO+202406302359]" in raw_url


async def test_search_with_categories_and_date_range(httpx_mock: HTTPXMock):
    """同时给定 categories 与 date 时两段都附加。"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_SEARCH_XML,
    )

    async with ArxivClient() as c:
        await c.search(
            "transformer",
            categories=["cs.AI"],
            date_from="2024-01-01",
            date_to="2024-12-31",
        )

    raw_url = str(httpx_mock.get_requests()[0].url)
    assert "cat:cs.AI" in raw_url
    assert "+TO+" in raw_url


# ---------------------------------------------------------------------------
# New raw fields: journal_ref, updated, version (Feature 2)
# ---------------------------------------------------------------------------

ARXIV_WITH_JOURNAL_REF_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <summary>Abstract text.</summary>
    <published>2017-06-12T17:57:34Z</published>
    <updated>2023-08-02T00:41:18Z</updated>
    <author><name>Ashish Vaswani</name></author>
    <link href="http://arxiv.org/abs/1706.03762v7" rel="alternate" type="text/html"/>
    <arxiv:journal_ref>Advances in Neural Information Processing Systems 30 (2017)</arxiv:journal_ref>
    <arxiv:comment>15 pages, 5 figures</arxiv:comment>
    <category term="cs.CL"/>
  </entry>
</feed>
"""


async def test_raw_journal_ref(httpx_mock: HTTPXMock):
    """raw['journal_ref'] 正确从 arxiv:journal_ref 解析"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_WITH_JOURNAL_REF_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("transformer")

    raw = resp.results[0].raw
    assert raw["journal_ref"] == "Advances in Neural Information Processing Systems 30 (2017)"


async def test_raw_updated_date(httpx_mock: HTTPXMock):
    """raw['updated'] 正确从 <updated> 元素提取日期字符串"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_WITH_JOURNAL_REF_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("transformer")

    raw = resp.results[0].raw
    assert raw["updated"] == "2023-08-02"


async def test_raw_version_extracted(httpx_mock: HTTPXMock):
    """raw['version'] 正确从 arXiv ID 中提取版本号"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_WITH_JOURNAL_REF_XML,
    )

    async with ArxivClient() as c:
        resp = await c.search("transformer")

    raw = resp.results[0].raw
    # ID 是 1706.03762v7，应提取出 "v7"
    assert raw["version"] == "v7"


async def test_raw_no_journal_ref(httpx_mock: HTTPXMock):
    """无 arxiv:journal_ref 时 raw['journal_ref'] 为 None"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_SEARCH_XML,  # 现有 fixture 无 journal_ref
    )

    async with ArxivClient() as c:
        resp = await c.search("test")

    raw = resp.results[0].raw
    assert raw.get("journal_ref") is None


async def test_raw_version_v1(httpx_mock: HTTPXMock):
    """v1 版本 ID 正确提取版本号"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_NO_DOI_XML,  # ID: 2301.00001v1
    )

    async with ArxivClient() as c:
        resp = await c.search("test")

    raw = resp.results[0].raw
    assert raw["version"] == "v1"


# ---------------------------------------------------------------------------
# search_all() async generator (Feature 3)
# ---------------------------------------------------------------------------

ARXIV_PAGE1_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2001.00001v1</id>
    <title>Paper One</title>
    <summary>Abstract one.</summary>
    <published>2020-01-01T00:00:00Z</published>
    <updated>2020-01-01T00:00:00Z</updated>
    <author><name>Author A</name></author>
    <link href="http://arxiv.org/abs/2001.00001v1" rel="alternate" type="text/html"/>
    <category term="cs.AI"/>
  </entry>
</feed>
"""

ARXIV_PAGE2_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2001.00002v1</id>
    <title>Paper Two</title>
    <summary>Abstract two.</summary>
    <published>2020-01-02T00:00:00Z</published>
    <updated>2020-01-02T00:00:00Z</updated>
    <author><name>Author B</name></author>
    <link href="http://arxiv.org/abs/2001.00002v1" rel="alternate" type="text/html"/>
    <category term="cs.LG"/>
  </entry>
</feed>
"""


async def test_search_all_yields_all_results(httpx_mock: HTTPXMock):
    """search_all() 自动分批请求并逐条 yield 所有结果"""
    # 第一次请求返回 page1（total=2），第二次返回 page2，第三次空（不会到达）
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_PAGE1_XML,
    )
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_PAGE2_XML,
    )

    papers = []
    async with ArxivClient() as c:
        async for paper in c.search_all("test", batch_size=1):
            papers.append(paper)

    assert len(papers) == 2
    assert papers[0].title == "Paper One"
    assert papers[1].title == "Paper Two"


async def test_search_all_stops_on_empty(httpx_mock: HTTPXMock):
    """search_all() 在 API 返回空批次时停止迭代"""
    httpx_mock.add_response(
        url=re.compile(r"http://export\.arxiv\.org/api/query.*"),
        text=ARXIV_EMPTY_XML,  # total=0, no entries
    )

    papers = []
    async with ArxivClient() as c:
        async for paper in c.search_all("nonexistent"):
            papers.append(paper)

    assert papers == []
