"""Zotero 客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.paper.zotero`` 中 ZoteroClient 的搜索、条目获取、全文提取、
集合列表、附件选择逻辑等。

测试清单：
- ``test_search_basic``：基本搜索解析
- ``test_search_with_tag_filter``：标签过滤搜索
- ``test_search_pagination``：分页偏移逻辑
- ``test_search_empty_results``：无结果处理
- ``test_search_filters_notes``：排除笔记/附件/注释
- ``test_get_item``：单条目获取
- ``test_get_fulltext_from_parent``：从父条目查找附件后提取全文
- ``test_get_fulltext_direct_attachment``：直接附件全文提取
- ``test_get_fulltext_no_attachment``：无可用附件时抛异常
- ``test_list_collections``：集合列表
- ``test_pick_best_attachment_prefers_pdf``：附件选择优先 PDF
- ``test_pick_best_attachment_filters_linked``：排除 linked 附件
- ``test_parse_item_minimal``：最小字段解析
- ``test_config_error_no_api_key``：无 API Key 抛 ConfigError
- ``test_config_error_no_library_id``：无 Library ID 抛 ConfigError
- ``test_group_library_path``：群组库路径正确性
- ``test_backoff_header_respected``：Backoff 头处理
"""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.core.exceptions import ConfigError, NotFoundError
from souwen.models import SourceType
from souwen.paper.zotero import ZoteroClient


# ---------------------------------------------------------------------------
# Fixtures & mock data
# ---------------------------------------------------------------------------

ZOTERO_ITEM_1 = {
    "key": "ABCD1234",
    "version": 42,
    "data": {
        "key": "ABCD1234",
        "itemType": "journalArticle",
        "title": "Attention Is All You Need",
        "creators": [
            {"creatorType": "author", "firstName": "Ashish", "lastName": "Vaswani"},
            {"creatorType": "author", "name": "Google Brain Team"},
        ],
        "date": "2017-06-12",
        "DOI": "10.1038/s41586-021-03819-2",
        "url": "https://arxiv.org/abs/1706.03762",
        "abstractNote": "The dominant sequence transduction models...",
        "publicationTitle": "Nature",
        "tags": [{"tag": "transformer"}, {"tag": "attention"}],
    },
    "meta": {"numChildren": 1},
}

ZOTERO_ITEM_NOTE = {
    "key": "NOTE0001",
    "data": {
        "key": "NOTE0001",
        "itemType": "note",
        "note": "<p>My note</p>",
        "tags": [],
    },
}

ZOTERO_ITEM_BOOK = {
    "key": "BOOK0001",
    "data": {
        "key": "BOOK0001",
        "itemType": "book",
        "title": "Deep Learning",
        "creators": [
            {"creatorType": "author", "firstName": "Ian", "lastName": "Goodfellow"},
        ],
        "date": "2016",
        "DOI": "",
        "url": "",
        "abstractNote": "",
        "bookTitle": "MIT Press Series",
        "tags": [],
    },
}

ZOTERO_ATTACHMENT_PDF = {
    "key": "PDF00001",
    "data": {
        "key": "PDF00001",
        "itemType": "attachment",
        "contentType": "application/pdf",
        "linkMode": "imported_file",
        "dateAdded": "2024-01-15T10:00:00Z",
        "tags": [],
    },
}

ZOTERO_ATTACHMENT_HTML = {
    "key": "HTML0001",
    "data": {
        "key": "HTML0001",
        "itemType": "attachment",
        "contentType": "text/html",
        "linkMode": "imported_url",
        "dateAdded": "2024-01-16T10:00:00Z",
        "tags": [],
    },
}

ZOTERO_ATTACHMENT_LINKED = {
    "key": "LINK0001",
    "data": {
        "key": "LINK0001",
        "itemType": "attachment",
        "contentType": "application/pdf",
        "linkMode": "linked_url",
        "dateAdded": "2024-01-17T10:00:00Z",
        "tags": [],
    },
}

ZOTERO_FULLTEXT = {
    "content": "The dominant sequence transduction models are based on complex...",
    "indexedPages": 15,
    "totalPages": 15,
    "indexedChars": 50000,
    "totalChars": 50000,
}

ZOTERO_COLLECTIONS = [
    {
        "key": "COL00001",
        "data": {"name": "Transformers", "parentCollection": False},
        "meta": {"numItems": 12},
    },
    {
        "key": "COL00002",
        "data": {"name": "NLP Subset", "parentCollection": "COL00001"},
        "meta": {"numItems": 5},
    },
]


@pytest.fixture()
def zotero_env(monkeypatch):
    """设置 Zotero 必要环境变量。"""
    monkeypatch.setenv("SOUWEN_ZOTERO_API_KEY", "test-zotero-key-123")
    monkeypatch.setenv("SOUWEN_ZOTERO_LIBRARY_ID", "9876543")
    monkeypatch.setenv("SOUWEN_ZOTERO_LIBRARY_TYPE", "user")
    from souwen.config import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_basic(httpx_mock: HTTPXMock, zotero_env):
    """基本搜索：解析条目、作者、DOI、日期。"""
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items\?.*"),
        json=[ZOTERO_ITEM_1],
        headers={"Total-Results": "1"},
    )
    async with ZoteroClient() as client:
        resp = await client.search("attention")

    assert resp.source == SourceType.ZOTERO
    assert resp.query == "attention"
    assert resp.total_results == 1
    assert len(resp.results) == 1

    paper = resp.results[0]
    assert paper.title == "Attention Is All You Need"
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Ashish Vaswani"
    assert paper.authors[1].name == "Google Brain Team"
    assert paper.doi == "10.1038/s41586-021-03819-2"
    assert paper.year == 2017
    assert paper.journal == "Nature"
    assert paper.raw["tags"] == ["transformer", "attention"]
    assert paper.raw["item_key"] == "ABCD1234"


@pytest.mark.asyncio
async def test_search_with_tag_filter(httpx_mock: HTTPXMock, zotero_env):
    """标签过滤搜索。"""
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items\?.*tag=transformer.*"),
        json=[ZOTERO_ITEM_1],
        headers={"Total-Results": "1"},
    )
    async with ZoteroClient() as client:
        resp = await client.search("attention", tag="transformer")

    assert len(resp.results) == 1


@pytest.mark.asyncio
async def test_search_pagination(httpx_mock: HTTPXMock, zotero_env):
    """分页偏移逻辑。"""
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items\?.*start=10.*"),
        json=[ZOTERO_ITEM_1],
        headers={"Total-Results": "50"},
    )
    async with ZoteroClient() as client:
        resp = await client.search("test", limit=10, start=10)

    assert resp.page == 2
    assert resp.per_page == 10
    assert resp.total_results == 50


@pytest.mark.asyncio
async def test_search_empty_results(httpx_mock: HTTPXMock, zotero_env):
    """无结果处理。"""
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items\?.*"),
        json=[],
        headers={"Total-Results": "0"},
    )
    async with ZoteroClient() as client:
        resp = await client.search("nonexistent_query_xyz")

    assert resp.total_results == 0
    assert len(resp.results) == 0


@pytest.mark.asyncio
async def test_search_filters_notes(httpx_mock: HTTPXMock, zotero_env):
    """客户端侧排除笔记/附件条目。"""
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items\?.*"),
        json=[ZOTERO_ITEM_1, ZOTERO_ITEM_NOTE],
        headers={"Total-Results": "2"},
    )
    async with ZoteroClient() as client:
        resp = await client.search("mixed")

    # 笔记被过滤，只剩 1 条
    assert len(resp.results) == 1
    assert resp.results[0].title == "Attention Is All You Need"


# ---------------------------------------------------------------------------
# Get item tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_item(httpx_mock: HTTPXMock, zotero_env):
    """单条目获取。"""
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items/ABCD1234$"),
        json=ZOTERO_ITEM_1,
    )
    async with ZoteroClient() as client:
        paper = await client.get_item("ABCD1234")

    assert paper.title == "Attention Is All You Need"
    assert paper.source == SourceType.ZOTERO


# ---------------------------------------------------------------------------
# Fulltext tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fulltext_from_parent(httpx_mock: HTTPXMock, zotero_env):
    """从父条目自动查找附件后提取全文。"""
    # 第 1 次请求：获取父条目
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items/ABCD1234$"),
        json=ZOTERO_ITEM_1,
    )
    # 第 2 次请求：获取子条目
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items/ABCD1234/children$"),
        json=[ZOTERO_ATTACHMENT_PDF, ZOTERO_ATTACHMENT_HTML],
    )
    # 第 3 次请求：获取全文
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items/PDF00001/fulltext$"),
        json=ZOTERO_FULLTEXT,
    )

    async with ZoteroClient() as client:
        result = await client.get_fulltext("ABCD1234")

    assert result["item_key"] == "ABCD1234"
    assert result["attachment_key"] == "PDF00001"
    assert "dominant sequence" in result["content"]
    assert result["word_count"] > 0
    assert result["indexed_pages"] == 15


@pytest.mark.asyncio
async def test_get_fulltext_direct_attachment(httpx_mock: HTTPXMock, zotero_env):
    """直接附件提取全文（跳过子条目查找）。"""
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items/PDF00001$"),
        json=ZOTERO_ATTACHMENT_PDF,
    )
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items/PDF00001/fulltext$"),
        json=ZOTERO_FULLTEXT,
    )

    async with ZoteroClient() as client:
        result = await client.get_fulltext("PDF00001")

    assert result["attachment_key"] == "PDF00001"
    assert result["content"] != ""


@pytest.mark.asyncio
async def test_get_fulltext_no_attachment(httpx_mock: HTTPXMock, zotero_env):
    """无可用附件时抛 NotFoundError。"""
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items/BOOK0001$"),
        json=ZOTERO_ITEM_BOOK,
    )
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items/BOOK0001/children$"),
        json=[ZOTERO_ATTACHMENT_LINKED],  # 仅 linked 附件，不可提取全文
    )

    async with ZoteroClient() as client:
        with pytest.raises(NotFoundError, match="没有可提取全文的附件"):
            await client.get_fulltext("BOOK0001")


# ---------------------------------------------------------------------------
# Collections test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_collections(httpx_mock: HTTPXMock, zotero_env):
    """集合列表解析。"""
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/collections$"),
        json=ZOTERO_COLLECTIONS,
    )
    async with ZoteroClient() as client:
        cols = await client.list_collections()

    assert len(cols) == 2
    assert cols[0]["name"] == "Transformers"
    assert cols[0]["num_items"] == 12
    assert cols[1]["parent"] == "COL00001"


# ---------------------------------------------------------------------------
# Attachment selection tests
# ---------------------------------------------------------------------------


def test_pick_best_attachment_prefers_pdf():
    """附件选择优先 PDF，按 dateAdded 倒序。"""
    key = ZoteroClient._pick_best_attachment([ZOTERO_ATTACHMENT_HTML, ZOTERO_ATTACHMENT_PDF])
    assert key == "PDF00001"


def test_pick_best_attachment_filters_linked():
    """排除 linked_url 模式的附件。"""
    key = ZoteroClient._pick_best_attachment([ZOTERO_ATTACHMENT_LINKED])
    assert key is None


def test_pick_best_attachment_falls_back_to_html():
    """无 PDF 时回退到 HTML。"""
    key = ZoteroClient._pick_best_attachment([ZOTERO_ATTACHMENT_HTML])
    assert key == "HTML0001"


# ---------------------------------------------------------------------------
# Parse item edge cases
# ---------------------------------------------------------------------------


def test_parse_item_minimal(zotero_env):
    """最小字段条目解析不崩溃。"""
    minimal = {
        "key": "MIN00001",
        "data": {
            "itemType": "webpage",
            "title": "Minimal Page",
            "creators": [],
            "date": "",
            "DOI": "",
            "url": "",
            "abstractNote": "",
            "tags": [],
        },
    }
    client = ZoteroClient()
    paper = client._parse_item(minimal)
    assert paper.title == "Minimal Page"
    assert paper.doi is None
    assert paper.year is None
    assert paper.authors == []
    # source_url 使用 API 路径作为回退
    assert "/items/MIN00001" in paper.source_url


def test_parse_item_book_fields(zotero_env):
    """图书条目的 journal 从 bookTitle 取得。"""
    client = ZoteroClient()
    paper = client._parse_item(ZOTERO_ITEM_BOOK)
    assert paper.title == "Deep Learning"
    assert paper.journal == "MIT Press Series"


# ---------------------------------------------------------------------------
# Config error tests
# ---------------------------------------------------------------------------


def test_config_error_no_api_key(monkeypatch):
    """无 API Key 时抛 ConfigError。"""
    monkeypatch.delenv("SOUWEN_ZOTERO_API_KEY", raising=False)
    monkeypatch.delenv("SOUWEN_ZOTERO_LIBRARY_ID", raising=False)
    from souwen.config import get_config

    get_config.cache_clear()
    try:
        with pytest.raises(ConfigError):
            ZoteroClient()
    finally:
        get_config.cache_clear()


def test_config_error_no_library_id(monkeypatch):
    """有 API Key 但无 Library ID 时抛 ConfigError。"""
    monkeypatch.setenv("SOUWEN_ZOTERO_API_KEY", "test-key")
    monkeypatch.delenv("SOUWEN_ZOTERO_LIBRARY_ID", raising=False)
    from souwen.config import get_config

    get_config.cache_clear()
    try:
        with pytest.raises(ConfigError):
            ZoteroClient()
    finally:
        get_config.cache_clear()


# ---------------------------------------------------------------------------
# Group library path
# ---------------------------------------------------------------------------


def test_group_library_path(monkeypatch):
    """群组库路径使用 /groups/ 前缀。"""
    monkeypatch.setenv("SOUWEN_ZOTERO_API_KEY", "test-key")
    monkeypatch.setenv("SOUWEN_ZOTERO_LIBRARY_ID", "12345")
    monkeypatch.setenv("SOUWEN_ZOTERO_LIBRARY_TYPE", "group")
    from souwen.config import get_config

    get_config.cache_clear()
    try:
        client = ZoteroClient()
        assert client._base_path == "/groups/12345"
    finally:
        get_config.cache_clear()


# ---------------------------------------------------------------------------
# Backoff header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backoff_header_respected(httpx_mock: HTTPXMock, zotero_env):
    """Backoff 头正常处理不崩溃（不真正 sleep，仅验证逻辑路径）。"""
    httpx_mock.add_response(
        url=re.compile(r".*/users/9876543/items\?.*"),
        json=[ZOTERO_ITEM_1],
        headers={"Total-Results": "1", "Backoff": "0.01"},
    )
    async with ZoteroClient() as client:
        resp = await client.search("backoff_test")

    assert len(resp.results) == 1
