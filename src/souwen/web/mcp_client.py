"""通用 MCP 客户端 — 连接任意远程 MCP Server 并调用其 Tools

文件用途：
    提供通用的 Model Context Protocol (MCP) 客户端，支持连接任意远程 MCP Server，
    发现 Tools 并进行调用。支持 Streamable HTTP（新协议）和 SSE（旧协议）两种传输方式。

函数/类清单：
    MCPToolError（异常类）
        - 功能：MCP 工具调用失败时抛出的异常

    MCPToolInfo（TypedDict）
        - 功能：工具元数据描述

    MCPClient（类）
        - 功能：通用 MCP 客户端，连接远程 MCP Server
        - 主要方法：
            * list_tools() → list[MCPToolInfo]
            * call_tool(name, arguments) → CallToolResult
        - 用法：必须作为 async context manager 使用

模块依赖：
    - mcp（可选）: 官方 MCP Python SDK（pip install mcp）
    - contextlib: AsyncExitStack 管理嵌套上下文
    - logging: 日志记录

技术要点：
    - 使用 AsyncExitStack 管理嵌套上下文（transport + session），避免跨任务 cancel scope 问题
    - streamablehttp_client 返回 3 元组 (read, write, get_session_id)
    - sse_client 返回 2 元组 (read, write)
    - call_tool 返回原始 CallToolResult，由上层（如 MCPFetchClient）负责解析
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any, TypedDict

logger = logging.getLogger("souwen.web.mcp_client")


class MCPToolError(Exception):
    """MCP 工具调用返回错误"""

    pass


class MCPToolInfo(TypedDict):
    """MCP 工具元数据"""

    name: str
    description: str
    schema: dict[str, Any]


class MCPClient:
    """通用 MCP 客户端

    连接远程 MCP Server，发现并调用其提供的 Tools。
    支持 Streamable HTTP（推荐）和 SSE（兼容旧版）两种传输。

    必须作为 async context manager 使用:
        async with MCPClient(url="https://server.example/mcp") as client:
            tools = await client.list_tools()
            result = await client.call_tool("fetch", {"url": "https://example.com"})

    Attributes:
        url: MCP Server 端点 URL
        headers: 附加 HTTP 请求头（如认证 token）
        transport: 传输方式 ("streamable_http" 或 "sse")
        timeout: 工具调用超时秒数
    """

    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        transport: str = "streamable_http",
        timeout: float = 30.0,
    ):
        if not url or not url.startswith(("http://", "https://")):
            raise ValueError(f"MCP Server URL 必须以 http:// 或 https:// 开头: {url!r}")

        self.url = url
        self.headers = headers or {}
        self.transport = transport
        self.timeout = timeout
        self._session: Any = None
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> MCPClient:
        try:
            from mcp import ClientSession  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "MCP SDK 未安装。请执行: pip install mcp\n"
                '或在源码目录安装完整依赖: pip install -e ".[mcp]"'
            ) from e

        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        try:
            if self.transport == "streamable_http":
                transport_cm = streamablehttp_client(url=self.url, headers=self.headers)
                # streamablehttp_client yields (read, write, get_session_id)
                read_stream, write_stream, _get_session_id = await self._stack.enter_async_context(
                    transport_cm
                )
            elif self.transport == "sse":
                from mcp.client.sse import sse_client

                transport_cm = sse_client(url=self.url, headers=self.headers)
                # sse_client yields (read, write)
                read_stream, write_stream = await self._stack.enter_async_context(transport_cm)
            else:
                raise ValueError(
                    f"不支持的 MCP 传输方式: {self.transport!r}（支持: streamable_http, sse）"
                )

            self._session = await self._stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self._session.initialize()
            logger.info("MCP 连接建立: url=%s transport=%s", self.url, self.transport)

        except Exception:
            await self._stack.__aexit__(None, None, None)
            self._stack = None
            raise

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool | None:
        if self._stack:
            result = await self._stack.__aexit__(exc_type, exc_val, exc_tb)
            self._stack = None
            self._session = None
            return result
        return None

    async def list_tools(self) -> list[MCPToolInfo]:
        """列出 MCP Server 上所有可用工具

        Returns:
            工具信息列表，每项包含 name, description, schema
        """
        if not self._session:
            raise RuntimeError("MCPClient 未连接，请在 async with 块中使用")

        result = await self._session.list_tools()
        tools: list[MCPToolInfo] = []
        for t in result.tools:
            tools.append(
                MCPToolInfo(
                    name=t.name,
                    description=getattr(t, "description", "") or "",
                    schema=getattr(t, "inputSchema", {}) or {},
                )
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用 MCP Server 上的指定工具

        Args:
            name: 工具名称
            arguments: 工具参数字典

        Returns:
            原始 CallToolResult 对象

        Raises:
            MCPToolError: 工具返回 isError=True 时抛出
            RuntimeError: 未连接时调用
        """
        if not self._session:
            raise RuntimeError("MCPClient 未连接，请在 async with 块中使用")

        from datetime import timedelta

        result = await self._session.call_tool(
            name,
            arguments=arguments or {},
            read_timeout_seconds=timedelta(seconds=self.timeout),
        )

        # 检查工具调用是否返回错误
        if getattr(result, "isError", False):
            error_texts = []
            for content in result.content:
                if hasattr(content, "text"):
                    error_texts.append(content.text)
            error_msg = "\n".join(error_texts) or f"MCP 工具 '{name}' 返回错误"
            raise MCPToolError(error_msg)

        return result

    def extract_text(self, result: Any) -> str:
        """从 CallToolResult 中提取文本内容

        仅提取 TextContent 类型的内容，忽略图片等二进制内容。

        Args:
            result: call_tool() 的返回值

        Returns:
            拼接后的文本字符串
        """
        texts: list[str] = []
        for content in result.content:
            # 优先使用类型判断，回退到鸭子类型
            if hasattr(content, "text") and hasattr(content, "type") and content.type == "text":
                texts.append(content.text)
            elif hasattr(content, "text") and not hasattr(content, "type"):
                texts.append(content.text)
        return "\n".join(texts)
