"""Wayback Machine 客户端单元测试"""

import pytest

from souwen.models import WaybackCDXResponse, WaybackSnapshot
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
