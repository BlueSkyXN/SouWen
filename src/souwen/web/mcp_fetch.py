"""MCP Fetch Provider — 通过 MCP Server 的 fetch tool 抓取网页内容

文件用途：
    基于通用 MCPClient 的网页内容抓取提供者。连接远程 MCP fetch server
    （如 mcp-server-fetch），调用其 fetch 工具获取 URL 内容（Markdown 格式），
    并转换为 SouWen 统一的 FetchResult/FetchResponse 格式。

函数/类清单：
    MCPFetchClient（类）
        - 功能：MCP 内容抓取客户端
        - 主要方法：
            * fetch(url, timeout) → FetchResult
            * fetch_batch(urls, max_concurrency, timeout) → FetchResponse
        - 用法：必须作为 async context manager 使用

模块依赖：
    - souwen.web.mcp_client: MCPClient 通用客户端
    - souwen.models: FetchResult, FetchResponse 数据模型
    - souwen.config: get_config() 配置读取
    - asyncio: 并发控制（Semaphore）

技术要点：
    - 使用 Semaphore 限制并发 MCP 调用（默认 4），避免单次失败导致整个 session 崩溃
    - 单个 URL 失败不影响其他 URL 的抓取
    - fetch 工具的参数映射可通过 tool_name 和 url_argument 配置
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from souwen.config import get_config
from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.mcp_fetch")

# 默认并发限制（MCP 单 session 内的并发工具调用数）
_DEFAULT_CONCURRENCY = 4


class MCPFetchClient:
    """MCP 内容抓取客户端

    连接远程 MCP fetch server，调用其 fetch tool 获取网页内容（Markdown 格式）。
    遵循 SouWen fetch provider 标准接口。

    配置项（souwen.yaml / 环境变量）：
        - mcp_server_url: MCP Server 端点 URL（必需）
        - mcp_transport: 传输方式（streamable_http 或 sse，默认 streamable_http）
        - mcp_fetch_tool_name: 抓取工具名称（默认 "fetch"）
        - mcp_extra_headers: 附加请求头（JSON 字典）

    用法:
        async with MCPFetchClient() as client:
            response = await client.fetch_batch(["https://example.com"], timeout=30)
    """

    PROVIDER_NAME = "mcp"

    def __init__(
        self,
        server_url: str | None = None,
        *,
        transport: str | None = None,
        tool_name: str | None = None,
        headers: dict[str, str] | None = None,
        max_concurrency: int = _DEFAULT_CONCURRENCY,
    ):
        config = get_config()

        self._server_url = server_url or getattr(config, "mcp_server_url", None)
        if not self._server_url:
            raise ValueError(
                "MCP Server URL 未配置。请设置环境变量 SOUWEN_MCP_SERVER_URL "
                "或在 souwen.yaml 中配置 mcp_server_url"
            )

        self._transport = transport or getattr(config, "mcp_transport", "streamable_http")
        self._tool_name = tool_name or getattr(config, "mcp_fetch_tool_name", "fetch")
        self._headers = headers or getattr(config, "mcp_extra_headers", None) or {}
        self._max_concurrency = max_concurrency
        self._client: Any = None

    async def __aenter__(self) -> MCPFetchClient:
        from souwen.web.mcp_client import MCPClient

        self._client = MCPClient(
            url=self._server_url,
            headers=self._headers,
            transport=self._transport,
        )
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> bool | None:
        if self._client:
            result = await self._client.__aexit__(*exc)
            self._client = None
            return result
        return None

    async def fetch(self, url: str, *, timeout: float = 30.0) -> FetchResult:
        """抓取单个 URL

        Args:
            url: 目标 URL
            timeout: 超时秒数

        Returns:
            FetchResult，成功时包含 Markdown 内容
        """
        if not self._client:
            raise RuntimeError("MCPFetchClient 未连接，请在 async with 块中使用")

        try:
            # 临时覆盖客户端超时
            original_timeout = self._client.timeout
            self._client.timeout = timeout

            result = await self._client.call_tool(
                self._tool_name,
                arguments={"url": url},
            )

            self._client.timeout = original_timeout

            # 提取文本内容
            content = self._client.extract_text(result)

            if not content or not content.strip():
                return FetchResult(
                    url=url,
                    final_url=url,
                    source=self.PROVIDER_NAME,
                    error="MCP fetch 返回空内容",
                )

            # 提取标题（第一行如果是 # 开头）
            title = ""
            lines = content.strip().split("\n")
            if lines and lines[0].startswith("# "):
                title = lines[0].lstrip("# ").strip()

            return FetchResult(
                url=url,
                final_url=url,
                title=title,
                content=content,
                content_format="markdown",
                source=self.PROVIDER_NAME,
                snippet=content[:500] if content else "",
            )

        except Exception as exc:
            from souwen.web.mcp_client import MCPToolError

            error_msg = str(exc)
            if isinstance(exc, MCPToolError):
                error_msg = f"MCP 工具错误: {exc}"
            elif isinstance(exc, ImportError):
                error_msg = str(exc)
            else:
                error_msg = f"MCP 抓取失败: {exc}"

            logger.warning("MCP fetch 失败: url=%s err=%s", url, error_msg)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=error_msg,
            )

    async def fetch_batch(
        self,
        urls: list[str],
        *,
        max_concurrency: int | None = None,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL

        使用 Semaphore 限制并发数，单个 URL 失败不影响其他。

        Args:
            urls: URL 列表
            max_concurrency: 最大并发数（默认使用初始化时设置的值）
            timeout: 每个 URL 的超时秒数

        Returns:
            FetchResponse 聚合响应
        """
        if not urls:
            return FetchResponse(
                urls=[],
                results=[],
                total=0,
                total_ok=0,
                total_failed=0,
                provider=self.PROVIDER_NAME,
            )

        concurrency = max_concurrency or self._max_concurrency
        semaphore = asyncio.Semaphore(concurrency)

        async def _fetch_one(url: str) -> FetchResult:
            async with semaphore:
                return await self.fetch(url, timeout=timeout)

        results = await asyncio.gather(*[_fetch_one(u) for u in urls])

        ok_count = sum(1 for r in results if r.error is None)
        return FetchResponse(
            urls=urls,
            results=list(results),
            total=len(results),
            total_ok=ok_count,
            total_failed=len(results) - ok_count,
            provider=self.PROVIDER_NAME,
        )
