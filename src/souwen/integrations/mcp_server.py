"""SouWen MCP Server — 为 LLM 和 AI Agent 暴露搜索能力

Model Context Protocol (MCP) 集成，使 Claude Code、Cursor、Windsurf 等 AI 助手
能够直接调用 SouWen 的搜索、专利、网页搜索功能。

运行方式：
    python -m souwen.integrations.mcp_server

    或在 IDE 配置中（如 cursor/.cursor/rules/cline_mcp_config.json）：
    {
        "mcpServers": {
            "souwen": {
                "command": "python",
                "args": ["-m", "souwen.integrations.mcp_server"]
            }
        }
    }

主要工具（Tool）：
    search_papers
        - 搜索学术论文
        - 参数：query, sources (可选), limit (可选，默认 5)
        - 返回：论文列表 (JSON)

    search_patents
        - 搜索专利
        - 参数：query, sources (可选), limit (可选，默认 5)
        - 返回：专利列表 (JSON)

    web_search
        - 搜索网页
        - 参数：query, engines (可选), limit (可选，默认 10)
        - 返回：网页结果列表 (JSON)

    get_status
        - 检查 SouWen 数据源可用性
        - 参数：无
        - 返回：健康检查报告

主要函数：
    create_server() -> Server
        - 创建并配置 MCP 服务器
        - 注册所有工具和处理函数

    call_tool(name: str, arguments: dict) -> list[TextContent]
        - 工具调用处理器
        - 调用相应的 SouWen 搜索函数，返回 JSON 结果

    main() -> None
        - 异步主程序
        - 建立 stdio 流连接，运行 MCP 服务器

模块依赖：
    - mcp：Model Context Protocol SDK（可选依赖）
    - souwen.search：搜索函数
    - souwen.doctor：健康检查
"""

from __future__ import annotations

import asyncio
import json

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    HAS_MCP = True
except ImportError:
    HAS_MCP = False


def create_server() -> "Server":
    """创建并配置 MCP 服务器 — 注册工具和处理函数

    工具列表：
    1. search_papers - 论文搜索
    2. search_patents - 专利搜索
    3. web_search - 网页搜索
    4. get_status - 数据源健康检查

    Returns:
        mcp.server.Server 实例

    Raises:
        SystemExit：MCP SDK 未安装时退出
    """

    server = Server("souwen")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """返回 MCP 工具清单 — 由 MCP SDK 在客户端连接时调用"""
        return [
            Tool(
                name="search_papers",
                description=(
                    "搜索学术论文。支持 OpenAlex, Semantic Scholar, "
                    "Crossref, arXiv, DBLP, CORE, PubMed, Unpaywall。"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "数据源列表，默认 openalex,arxiv,crossref",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 5,
                            "description": "每源返回数量",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="search_patents",
                description=(
                    "搜索专利。支持 PatentsView, PQAI, EPO OPS, "
                    "USPTO, The Lens, CNIPA, PatSnap, Google Patents。"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "数据源列表，默认 google_patents",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 5,
                            "description": "每源返回数量",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="web_search",
                description="网页搜索。支持 21 个引擎，默认 DuckDuckGo + Bing。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "engines": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "引擎列表",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 10,
                            "description": "每引擎最大结果数",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="get_status",
                description="检查 SouWen 数据源可用性状态",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """工具调用处理器 — 调用对应的搜索函数

        参数：
            name: 工具名称（search_papers、search_patents、web_search、get_status）
            arguments: 工具参数字典

        Returns:
            list[TextContent]：单个文本内容项，包含 JSON 结果

        说明：
            所有异常均被捕获并返回为文本错误消息（避免服务崩溃）。
            结果格式化为 JSON 字符串，便于 LLM 解析。
        """
        try:
            if name == "search_papers":
                from souwen.search import search_papers

                sources = arguments.get("sources", ["openalex", "arxiv", "crossref"])
                limit = arguments.get("limit", 5)
                responses = await search_papers(arguments["query"], sources=sources, per_page=limit)
                result = [r.model_dump(mode="json") for r in responses]

            elif name == "search_patents":
                from souwen.search import search_patents

                sources = arguments.get("sources", ["google_patents"])
                limit = arguments.get("limit", 5)
                responses = await search_patents(
                    arguments["query"], sources=sources, per_page=limit
                )
                result = [r.model_dump(mode="json") for r in responses]

            elif name == "web_search":
                from souwen.web.search import web_search

                engines = arguments.get("engines")
                limit = arguments.get("limit", 10)
                response = await web_search(
                    arguments["query"], engines=engines, max_results_per_engine=limit
                )
                result = response.model_dump(mode="json")

            elif name == "get_status":
                from souwen.doctor import check_all, format_report

                results = check_all()
                result = format_report(results)

            else:
                result = f"Unknown tool: {name}"

            text = (
                json.dumps(result, ensure_ascii=False, indent=2)
                if isinstance(result, (dict, list))
                else str(result)
            )
            return [TextContent(type="text", text=text)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]

    return server


async def main() -> None:
    """MCP 服务器主程序 — 建立 stdio 连接并运行

    使用 stdio_server 建立与客户端（IDE）的双向通信，
    运行 MCP 协议处理循环。
    """
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
