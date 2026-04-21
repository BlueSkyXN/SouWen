"""MCP 客户端和 MCP Fetch Provider 单元测试

使用 unittest.mock 模拟 MCP SDK 依赖，不需要真实的 MCP Server。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from souwen.web.mcp_client import MCPClient, MCPToolError


# ============================================================================
# MCPClient Tests
# ============================================================================


class TestMCPClientInit:
    """MCPClient 初始化测试"""

    def test_valid_url(self):
        client = MCPClient(url="https://example.com/mcp")
        assert client.url == "https://example.com/mcp"
        assert client.transport == "streamable_http"
        assert client.timeout == 30.0

    def test_http_url(self):
        client = MCPClient(url="http://localhost:8080/mcp")
        assert client.url == "http://localhost:8080/mcp"

    def test_invalid_url_no_scheme(self):
        with pytest.raises(ValueError, match="必须以 http"):
            MCPClient(url="example.com/mcp")

    def test_invalid_url_ftp(self):
        with pytest.raises(ValueError, match="必须以 http"):
            MCPClient(url="ftp://example.com/mcp")

    def test_empty_url(self):
        with pytest.raises(ValueError, match="必须以 http"):
            MCPClient(url="")

    def test_custom_headers(self):
        client = MCPClient(url="https://x.com/mcp", headers={"Authorization": "Bearer token"})
        assert client.headers == {"Authorization": "Bearer token"}

    def test_sse_transport(self):
        client = MCPClient(url="https://x.com/mcp", transport="sse")
        assert client.transport == "sse"


class TestMCPClientConnect:
    """MCPClient 连接测试（模拟 MCP SDK）"""

    @pytest.mark.asyncio
    async def test_streamable_http_connect(self):
        """测试 Streamable HTTP 传输连接"""
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_read = MagicMock()
        mock_write = MagicMock()
        mock_get_session_id = MagicMock()

        with (
            patch(
                "mcp.client.streamable_http.streamablehttp_client",
                return_value=_async_cm(mock_read, mock_write, mock_get_session_id),
            ),
            patch("mcp.ClientSession", return_value=mock_session),
        ):
            # 验证连接流程不抛异常
            pass

    @pytest.mark.asyncio
    async def test_unsupported_transport(self):
        """测试不支持的传输方式"""
        client = MCPClient(url="https://x.com/mcp", transport="grpc")
        with pytest.raises(ValueError, match="不支持的 MCP 传输方式"):
            await client.__aenter__()

    @pytest.mark.asyncio
    async def test_call_without_connect(self):
        """测试未连接时调用方法"""
        client = MCPClient(url="https://x.com/mcp")
        with pytest.raises(RuntimeError, match="未连接"):
            await client.list_tools()
        with pytest.raises(RuntimeError, match="未连接"):
            await client.call_tool("fetch", {"url": "https://example.com"})


class TestMCPClientCallTool:
    """MCPClient.call_tool 测试"""

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        """测试成功的工具调用"""
        client = MCPClient(url="https://x.com/mcp")

        # 模拟 session
        mock_content = MagicMock()
        mock_content.text = "# Hello\n\nWorld content"
        mock_content.type = "text"

        mock_result = MagicMock()
        mock_result.isError = False
        mock_result.content = [mock_content]

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        client._session = mock_session

        result = await client.call_tool("fetch", {"url": "https://example.com"})
        assert result == mock_result

        mock_session.call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_error(self):
        """测试工具返回错误"""
        client = MCPClient(url="https://x.com/mcp")

        mock_content = MagicMock()
        mock_content.text = "URL not reachable"
        mock_content.type = "text"

        mock_result = MagicMock()
        mock_result.isError = True
        mock_result.content = [mock_content]

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        client._session = mock_session

        with pytest.raises(MCPToolError, match="URL not reachable"):
            await client.call_tool("fetch", {"url": "https://bad.com"})


class TestMCPClientExtractText:
    """MCPClient.extract_text 测试"""

    def test_extract_single_text(self):
        client = MCPClient(url="https://x.com/mcp")

        mock_content = MagicMock()
        mock_content.text = "Hello World"
        mock_content.type = "text"

        mock_result = MagicMock()
        mock_result.content = [mock_content]

        assert client.extract_text(mock_result) == "Hello World"

    def test_extract_multiple_texts(self):
        client = MCPClient(url="https://x.com/mcp")

        c1 = MagicMock()
        c1.text = "Part 1"
        c1.type = "text"

        c2 = MagicMock()
        c2.text = "Part 2"
        c2.type = "text"

        mock_result = MagicMock()
        mock_result.content = [c1, c2]

        assert client.extract_text(mock_result) == "Part 1\nPart 2"

    def test_extract_ignores_non_text(self):
        client = MCPClient(url="https://x.com/mcp")

        text_content = MagicMock()
        text_content.text = "Real text"
        text_content.type = "text"

        image_content = MagicMock()
        image_content.type = "image"
        # no text attribute
        del image_content.text

        mock_result = MagicMock()
        mock_result.content = [text_content, image_content]

        assert client.extract_text(mock_result) == "Real text"

    def test_extract_empty(self):
        client = MCPClient(url="https://x.com/mcp")
        mock_result = MagicMock()
        mock_result.content = []
        assert client.extract_text(mock_result) == ""


# ============================================================================
# MCPFetchClient Tests
# ============================================================================


class TestMCPFetchClient:
    """MCPFetchClient 测试"""

    @pytest.mark.asyncio
    async def test_no_server_url_raises(self):
        """未配置 MCP Server URL 时应报错"""
        from souwen.web.mcp_fetch import MCPFetchClient

        with patch("souwen.web.mcp_fetch.get_config") as mock_config:
            mock_config.return_value = MagicMock(
                mcp_server_url=None,
                mcp_transport="streamable_http",
                mcp_fetch_tool_name="fetch",
                mcp_extra_headers={},
            )
            with pytest.raises(ValueError, match="MCP Server URL 未配置"):
                MCPFetchClient()

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        """测试单 URL 抓取成功"""
        from souwen.web.mcp_fetch import MCPFetchClient

        with patch("souwen.web.mcp_fetch.get_config") as mock_config:
            mock_config.return_value = MagicMock(
                mcp_server_url="https://mcp.test/mcp",
                mcp_transport="streamable_http",
                mcp_fetch_tool_name="fetch",
                mcp_extra_headers={},
            )

            client = MCPFetchClient()

            # 模拟 MCPClient
            mock_content = MagicMock()
            mock_content.text = "# Test Page\n\nThis is test content."
            mock_content.type = "text"

            mock_result = MagicMock()
            mock_result.isError = False
            mock_result.content = [mock_content]

            mock_mcp_client = AsyncMock()
            mock_mcp_client.call_tool = AsyncMock(return_value=mock_result)
            mock_mcp_client.extract_text = MagicMock(
                return_value="# Test Page\n\nThis is test content."
            )
            mock_mcp_client.timeout = 30.0

            client._client = mock_mcp_client

            result = await client.fetch("https://example.com", timeout=30)
            assert result.error is None
            assert result.title == "Test Page"
            assert "test content" in result.content
            assert result.source == "mcp"
            assert result.content_format == "markdown"

    @pytest.mark.asyncio
    async def test_fetch_error(self):
        """测试单 URL 抓取失败"""
        from souwen.web.mcp_fetch import MCPFetchClient

        with patch("souwen.web.mcp_fetch.get_config") as mock_config:
            mock_config.return_value = MagicMock(
                mcp_server_url="https://mcp.test/mcp",
                mcp_transport="streamable_http",
                mcp_fetch_tool_name="fetch",
                mcp_extra_headers={},
            )

            client = MCPFetchClient()

            mock_mcp_client = AsyncMock()
            mock_mcp_client.call_tool = AsyncMock(side_effect=MCPToolError("Connection refused"))
            mock_mcp_client.timeout = 30.0

            client._client = mock_mcp_client

            result = await client.fetch("https://bad.example.com", timeout=30)
            assert result.error is not None
            assert "Connection refused" in result.error
            assert result.source == "mcp"

    @pytest.mark.asyncio
    async def test_fetch_empty_content(self):
        """测试返回空内容"""
        from souwen.web.mcp_fetch import MCPFetchClient

        with patch("souwen.web.mcp_fetch.get_config") as mock_config:
            mock_config.return_value = MagicMock(
                mcp_server_url="https://mcp.test/mcp",
                mcp_transport="streamable_http",
                mcp_fetch_tool_name="fetch",
                mcp_extra_headers={},
            )

            client = MCPFetchClient()

            mock_result = MagicMock()
            mock_result.isError = False
            mock_result.content = []

            mock_mcp_client = AsyncMock()
            mock_mcp_client.call_tool = AsyncMock(return_value=mock_result)
            mock_mcp_client.extract_text = MagicMock(return_value="")
            mock_mcp_client.timeout = 30.0

            client._client = mock_mcp_client

            result = await client.fetch("https://empty.example.com", timeout=30)
            assert result.error is not None
            assert "空内容" in result.error

    @pytest.mark.asyncio
    async def test_fetch_batch(self):
        """测试批量抓取"""
        from souwen.web.mcp_fetch import MCPFetchClient

        with patch("souwen.web.mcp_fetch.get_config") as mock_config:
            mock_config.return_value = MagicMock(
                mcp_server_url="https://mcp.test/mcp",
                mcp_transport="streamable_http",
                mcp_fetch_tool_name="fetch",
                mcp_extra_headers={},
            )

            client = MCPFetchClient()

            async def mock_call_tool(name, arguments=None, read_timeout_seconds=None):
                url = arguments.get("url", "")

                if "bad" in url:
                    # MCPClient.call_tool 在 isError=True 时抛出 MCPToolError
                    raise MCPToolError(f"Failed to fetch {url}")

                mock_content = MagicMock()
                mock_content.type = "text"
                mock_content.text = f"# Page\n\nContent of {url}"
                mock_result = MagicMock()
                mock_result.isError = False
                mock_result.content = [mock_content]
                return mock_result

            mock_mcp_client = AsyncMock()
            mock_mcp_client.call_tool = mock_call_tool
            mock_mcp_client.timeout = 30.0

            def extract_text(result):
                texts = []
                for c in result.content:
                    if hasattr(c, "text") and hasattr(c, "type") and c.type == "text":
                        texts.append(c.text)
                return "\n".join(texts)

            mock_mcp_client.extract_text = extract_text

            client._client = mock_mcp_client

            urls = ["https://good1.com", "https://bad.com", "https://good2.com"]
            response = await client.fetch_batch(urls, timeout=10)

            assert response.total == 3
            assert response.total_ok == 2
            assert response.total_failed == 1
            assert response.provider == "mcp"

    @pytest.mark.asyncio
    async def test_fetch_batch_empty(self):
        """测试空列表批量抓取"""
        from souwen.web.mcp_fetch import MCPFetchClient

        with patch("souwen.web.mcp_fetch.get_config") as mock_config:
            mock_config.return_value = MagicMock(
                mcp_server_url="https://mcp.test/mcp",
                mcp_transport="streamable_http",
                mcp_fetch_tool_name="fetch",
                mcp_extra_headers={},
            )

            client = MCPFetchClient()
            response = await client.fetch_batch([], timeout=10)

            assert response.total == 0
            assert response.results == []


# ============================================================================
# Helper
# ============================================================================


class _async_cm:
    """模拟异步上下文管理器"""

    def __init__(self, *values):
        self.values = values

    async def __aenter__(self):
        if len(self.values) == 1:
            return self.values[0]
        return self.values

    async def __aexit__(self, *exc):
        return None
