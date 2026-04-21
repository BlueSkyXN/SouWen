"""Wayback Machine 客户端单元测试"""

import re

import httpx
import pytest
from pytest_httpx import HTTPXMock

from souwen.models import (
    WaybackAvailability,
    WaybackCDXResponse,
    WaybackSaveResult,
    WaybackSnapshot,
)
from souwen.web.wayback import WaybackClient


class TestWaybackClient:
    """测试 WaybackClient 的各种功能"""

    @pytest.mark.asyncio
    async def test_format_published_date(self):
        """测试时间戳格式化为日期"""
        assert WaybackClient._format_published_date("20230115120000") == "2023-01-15"
        assert WaybackClient._format_published_date("20231231235959") == "2023-12-31"
        assert WaybackClient._format_published_date("invalid") is None
        assert WaybackClient._format_published_date("") is None

    @pytest.mark.asyncio
    async def test_to_raw_snapshot_url(self):
        """测试快照 URL 添加 id_ 修饰符"""
        url = "http://web.archive.org/web/20230101000000/http://example.com/"
        expected = "http://web.archive.org/web/20230101000000id_/http://example.com/"
        assert WaybackClient._to_raw_snapshot_url(url) == expected

        # 测试已经有 id_ 的情况
        url_with_id = "http://web.archive.org/web/20230101000000id_/http://example.com/"
        # 只替换第一次出现的，所以不会重复添加
        assert WaybackClient._to_raw_snapshot_url(url_with_id) == url_with_id

    @pytest.mark.asyncio
    async def test_wayback_snapshot_model(self):
        """测试 WaybackSnapshot 数据模型"""
        snapshot = WaybackSnapshot(
            timestamp="20230115120000",
            url="http://example.com/",
            archive_url="https://web.archive.org/web/20230115120000/http://example.com/",
            status_code=200,
            mime_type="text/html",
            digest="ABC123DEF456",
            length=12345,
            published_date="2023-01-15",
        )

        assert snapshot.timestamp == "20230115120000"
        assert snapshot.url == "http://example.com/"
        assert snapshot.status_code == 200
        assert snapshot.mime_type == "text/html"
        assert snapshot.published_date == "2023-01-15"
        assert snapshot.length == 12345

    @pytest.mark.asyncio
    async def test_wayback_cdx_response_model(self):
        """测试 WaybackCDXResponse 数据模型"""
        snapshot1 = WaybackSnapshot(
            timestamp="20230115120000",
            url="http://example.com/",
            archive_url="https://web.archive.org/web/20230115120000/http://example.com/",
        )
        snapshot2 = WaybackSnapshot(
            timestamp="20230116120000",
            url="http://example.com/",
            archive_url="https://web.archive.org/web/20230116120000/http://example.com/",
        )

        response = WaybackCDXResponse(
            url="example.com",
            snapshots=[snapshot1, snapshot2],
            total=2,
            from_date="20230101",
            to_date="20231231",
            filter_status=[200],
            filter_mime="text/html",
        )

        assert response.url == "example.com"
        assert len(response.snapshots) == 2
        assert response.total == 2
        assert response.from_date == "20230101"
        assert response.to_date == "20231231"
        assert response.filter_status == [200]
        assert response.filter_mime == "text/html"
        assert response.error is None

    @pytest.mark.asyncio
    async def test_wayback_cdx_response_with_error(self):
        """测试带错误信息的 CDX 响应"""
        response = WaybackCDXResponse(
            url="example.com",
            snapshots=[],
            total=0,
            error="连接超时",
        )

        assert response.url == "example.com"
        assert len(response.snapshots) == 0
        assert response.total == 0
        assert response.error == "连接超时"

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """测试客户端初始化"""
        async with WaybackClient() as client:
            assert client.ENGINE_NAME == "wayback"
            assert client.BASE_URL == "https://web.archive.org"
            assert client.PROVIDER_NAME == "wayback"

    # 下面的测试需要网络连接，在 CI 中可能会失败
    # 可以使用 @pytest.mark.skip 跳过或使用 mock

    @pytest.mark.skip(reason="需要网络连接")
    @pytest.mark.asyncio
    async def test_query_snapshots_basic(self):
        """测试基本的快照查询（需要网络）"""
        async with WaybackClient() as client:
            response = await client.query_snapshots(
                url="example.com",
                limit=5,
            )

            assert response.url == "example.com"
            assert response.error is None or isinstance(response.error, str)
            assert isinstance(response.snapshots, list)
            assert response.total >= 0

    @pytest.mark.skip(reason="需要网络连接")
    @pytest.mark.asyncio
    async def test_query_snapshots_with_filters(self):
        """测试带过滤条件的快照查询（需要网络）"""
        async with WaybackClient() as client:
            response = await client.query_snapshots(
                url="example.com",
                from_date="2023-01-01",
                to_date="2023-12-31",
                filter_status=[200],
                filter_mime="text/html",
                limit=10,
            )

            assert response.url == "example.com"
            assert response.from_date == "20230101"
            assert response.to_date == "20231231"
            assert response.filter_status == [200]
            assert response.filter_mime == "text/html"

            if response.error is None and len(response.snapshots) > 0:
                # 验证所有快照都符合过滤条件
                for snapshot in response.snapshots:
                    assert snapshot.status_code == 200
                    # 日期应该在 2023 年范围内
                    if snapshot.published_date:
                        assert snapshot.published_date.startswith("2023")


# ---------------------------------------------------------------------------
# query_snapshots() — 基于 pytest-httpx 的 mock 单元测试
# ---------------------------------------------------------------------------

CDX_URL_PATTERN = re.compile(r"https://web\.archive\.org/cdx/search/cdx")

# 标准 CDX 响应：第一行是字段名，后续行是数据值
CDX_FIELDS = ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"]
CDX_SAMPLE_RESPONSE = [
    CDX_FIELDS,
    [
        "com,example)/",
        "20230115120000",
        "http://example.com/",
        "text/html",
        "200",
        "ABC123DEF456",
        "1234",
    ],
    [
        "com,example)/",
        "20230516093000",
        "http://example.com/",
        "text/html",
        "301",
        "XYZ789",
        "567",
    ],
]


async def test_query_snapshots_parses_cdx_response(httpx_mock: HTTPXMock):
    """正常解析：CDX JSON → WaybackSnapshot 列表"""
    httpx_mock.add_response(url=CDX_URL_PATTERN, json=CDX_SAMPLE_RESPONSE)

    async with WaybackClient() as client:
        resp = await client.query_snapshots(url="example.com")

    assert resp.error is None
    assert resp.url == "example.com"
    assert resp.total == 2
    assert len(resp.snapshots) == 2

    snap0 = resp.snapshots[0]
    assert snap0.timestamp == "20230115120000"
    assert snap0.url == "http://example.com/"
    assert snap0.status_code == 200
    assert snap0.mime_type == "text/html"
    assert snap0.digest == "ABC123DEF456"
    assert snap0.length == 1234
    assert snap0.published_date == "2023-01-15"
    assert snap0.archive_url == "https://web.archive.org/web/20230115120000/http://example.com/"

    assert resp.snapshots[1].status_code == 301
    assert resp.snapshots[1].length == 567


async def test_query_snapshots_passes_filter_params(httpx_mock: HTTPXMock):
    """验证 status_code / mime / collapse / limit / 日期 参数正确传递给 CDX API"""
    httpx_mock.add_response(url=CDX_URL_PATTERN, json=[CDX_FIELDS])

    async with WaybackClient() as client:
        resp = await client.query_snapshots(
            url="example.com",
            from_date="2023-01-01",
            to_date="2023-12-31",
            filter_status=[200, 301],
            filter_mime="text/html",
            limit=50,
            collapse="timestamp:8",
        )

    # 验证响应元数据
    assert resp.from_date == "20230101"
    assert resp.to_date == "20231231"
    assert resp.filter_status == [200, 301]
    assert resp.filter_mime == "text/html"

    # 验证实际发出的请求参数
    request = httpx_mock.get_requests()[0]
    qs = request.url.params
    assert qs["url"] == "example.com"
    assert qs["output"] == "json"
    assert qs["from"] == "20230101"
    assert qs["to"] == "20231231"
    assert qs["limit"] == "50"
    assert qs["collapse"] == "timestamp:8"
    # filter 是多值参数：状态码 + mime
    filters = qs.get_list("filter")
    assert "statuscode:200" in filters
    assert "statuscode:301" in filters
    assert "mimetype:text/html" in filters


async def test_query_snapshots_empty_result(httpx_mock: HTTPXMock):
    """空结果：CDX 仅返回字段头或空数组"""
    httpx_mock.add_response(url=CDX_URL_PATTERN, json=[CDX_FIELDS])

    async with WaybackClient() as client:
        resp = await client.query_snapshots(url="no-such-domain.invalid")

    assert resp.error is None
    assert resp.total == 0
    assert resp.snapshots == []


async def test_query_snapshots_skips_dirty_rows(httpx_mock: HTTPXMock):
    """脏数据：长度不足/类型不符的行应被跳过"""
    dirty_response = [
        CDX_FIELDS,
        ["com,example)/", "20230101000000"],  # 字段不足
        "not-a-list",  # 类型错误
        [
            "com,example)/",
            "20230301000000",
            "http://example.com/",
            "text/html",
            "200",
            "DIGEST",
            "100",
        ],
    ]
    httpx_mock.add_response(url=CDX_URL_PATTERN, json=dirty_response)

    async with WaybackClient() as client:
        resp = await client.query_snapshots(url="example.com")

    assert resp.error is None
    assert resp.total == 1
    assert resp.snapshots[0].timestamp == "20230301000000"


async def test_query_snapshots_handles_non_string_status_and_length(httpx_mock: HTTPXMock):
    """类型安全：CDX 偶尔返回 int 或 None，不应抛 AttributeError"""
    response = [
        CDX_FIELDS,
        # status / length 是 int
        ["com,example)/", "20230101000000", "http://example.com/", "text/html", 200, "D1", 1024],
        # status / length 是 None
        ["com,example)/", "20230102000000", "http://example.com/", "text/html", None, "D2", None],
        # length 是非数字脏字符串
        ["com,example)/", "20230103000000", "http://example.com/", "text/html", "abc", "D3", "n/a"],
    ]
    httpx_mock.add_response(url=CDX_URL_PATTERN, json=response)

    async with WaybackClient() as client:
        resp = await client.query_snapshots(url="example.com")

    assert resp.error is None
    assert len(resp.snapshots) == 3
    # int 类型应被正确解析
    assert resp.snapshots[0].status_code == 200
    assert resp.snapshots[0].length == 1024
    # None 应回退到默认值
    assert resp.snapshots[1].status_code == 200
    assert resp.snapshots[1].length == 0
    # 非数字字符串应回退到默认值，不报错
    assert resp.snapshots[2].status_code == 200
    assert resp.snapshots[2].length == 0


async def test_query_snapshots_network_error_into_error_field(httpx_mock: HTTPXMock):
    """网络异常应被捕获并写入 WaybackCDXResponse.error，不向上抛"""
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    async with WaybackClient() as client:
        resp = await client.query_snapshots(url="example.com")

    assert resp.snapshots == []
    assert resp.total == 0
    assert resp.error is not None
    assert "connection refused" in resp.error or "ConnectError" in resp.error


async def test_query_snapshots_http_error_into_error_field(httpx_mock: HTTPXMock):
    """HTTP 5xx 应被 raise_for_status 捕获并写入 error 字段"""
    httpx_mock.add_response(url=CDX_URL_PATTERN, status_code=503, text="Service Unavailable")

    async with WaybackClient() as client:
        resp = await client.query_snapshots(url="example.com")

    assert resp.snapshots == []
    assert resp.total == 0
    assert resp.error is not None


# ---------------------------------------------------------------------------
# check_availability() — Availability API mock 测试
# ---------------------------------------------------------------------------

AVAILABILITY_URL_PATTERN = re.compile(r"https://archive\.org/wayback/available")


async def test_check_availability_found(httpx_mock: HTTPXMock):
    """有快照时返回结构化 WaybackAvailability"""
    httpx_mock.add_response(
        url=AVAILABILITY_URL_PATTERN,
        json={
            "url": "example.com",
            "archived_snapshots": {
                "closest": {
                    "status": "200",
                    "available": True,
                    "url": "http://web.archive.org/web/20240101000000/http://example.com/",
                    "timestamp": "20240101000000",
                }
            },
        },
    )

    async with WaybackClient() as client:
        resp = await client.check_availability("http://example.com/")

    assert isinstance(resp, WaybackAvailability)
    assert resp.error is None
    assert resp.url == "http://example.com/"
    assert resp.available is True
    assert resp.snapshot_url == "http://web.archive.org/web/20240101000000/http://example.com/"
    assert resp.timestamp == "20240101000000"
    assert resp.published_date == "2024-01-01"
    assert resp.status_code == 200


async def test_check_availability_not_found(httpx_mock: HTTPXMock):
    """无快照时 available=False，snapshot_url=None"""
    httpx_mock.add_response(
        url=AVAILABILITY_URL_PATTERN,
        json={"url": "no-such-domain.invalid", "archived_snapshots": {}},
    )

    async with WaybackClient() as client:
        resp = await client.check_availability("no-such-domain.invalid")

    assert resp.error is None
    assert resp.available is False
    assert resp.snapshot_url is None
    assert resp.timestamp is None
    assert resp.published_date is None
    assert resp.status_code is None


async def test_check_availability_with_timestamp(httpx_mock: HTTPXMock):
    """指定 timestamp 时应作为查询参数传递给 archive.org"""
    httpx_mock.add_response(
        url=AVAILABILITY_URL_PATTERN,
        json={
            "url": "example.com",
            "archived_snapshots": {
                "closest": {
                    "status": "200",
                    "available": True,
                    "url": "http://web.archive.org/web/20200615120000/http://example.com/",
                    "timestamp": "20200615120000",
                }
            },
        },
    )

    async with WaybackClient() as client:
        resp = await client.check_availability("http://example.com/", timestamp="20200615")

    assert resp.available is True
    assert resp.timestamp == "20200615120000"
    assert resp.published_date == "2020-06-15"

    # 验证请求带上了 timestamp 参数
    request = httpx_mock.get_requests()[0]
    qs = request.url.params
    assert qs["url"] == "http://example.com/"
    assert qs["timestamp"] == "20200615"


async def test_check_availability_error(httpx_mock: HTTPXMock):
    """网络错误应封装到 error 字段，不向上抛"""
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    async with WaybackClient() as client:
        resp = await client.check_availability("http://example.com/")

    assert resp.available is False
    assert resp.snapshot_url is None
    assert resp.error is not None
    assert "connection refused" in resp.error or "ConnectError" in resp.error


# ---------------------------------------------------------------------------
# save_page() — Save Page Now mock 测试
# ---------------------------------------------------------------------------

SAVE_URL_PATTERN = re.compile(r"https://web\.archive\.org/save/")


async def test_save_page_success(httpx_mock: HTTPXMock):
    """成功触发存档：通过 Content-Location header 返回快照 URL"""
    httpx_mock.add_response(
        url=SAVE_URL_PATTERN,
        method="POST",
        status_code=200,
        headers={"Content-Location": "/web/20240501123045/http://example.com/"},
        text="<html>Saved</html>",
    )

    async with WaybackClient() as client:
        resp = await client.save_page("http://example.com/")

    assert isinstance(resp, WaybackSaveResult)
    assert resp.success is True
    assert resp.url == "http://example.com/"
    assert resp.snapshot_url == "https://web.archive.org/web/20240501123045/http://example.com/"
    assert resp.timestamp == "20240501123045"
    assert resp.error is None


async def test_save_page_success_via_html_body(httpx_mock: HTTPXMock):
    """无 Location header 时，从响应体中正则提取 /web/<ts>/<url>"""
    body = '<html><a href="/web/20240701080910/http://example.com/page">snapshot</a></html>'
    httpx_mock.add_response(
        url=SAVE_URL_PATTERN,
        method="POST",
        status_code=200,
        text=body,
    )

    async with WaybackClient() as client:
        resp = await client.save_page("http://example.com/page")

    assert resp.success is True
    assert resp.snapshot_url == "https://web.archive.org/web/20240701080910/http://example.com/page"
    assert resp.timestamp == "20240701080910"


async def test_save_page_error(httpx_mock: HTTPXMock):
    """网络异常封装到 error 字段"""
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    async with WaybackClient() as client:
        resp = await client.save_page("http://example.com/")

    assert resp.success is False
    assert resp.snapshot_url is None
    assert resp.error is not None
    assert "connection refused" in resp.error or "ConnectError" in resp.error


async def test_save_page_http_error_no_snapshot(httpx_mock: HTTPXMock):
    """非 2xx/3xx 且无快照 URL 时 success=False，error 描述"""
    httpx_mock.add_response(
        url=SAVE_URL_PATTERN,
        method="POST",
        status_code=429,
        text="Too Many Requests",
    )

    async with WaybackClient() as client:
        resp = await client.save_page("http://example.com/")

    assert resp.success is False
    assert resp.snapshot_url is None
    assert resp.error is not None
    assert "429" in resp.error
