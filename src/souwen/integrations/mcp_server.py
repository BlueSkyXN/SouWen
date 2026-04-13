"""SouWen MCP Server — 将搜索能力暴露为 MCP 工具

让 Claude Code、Cursor、Windsurf 等 AI Agent 直接调用 SouWen 搜索。

运行: python -m souwen.integrations.mcp_server
"""

from __future__ import annotations

import asyncio
import json
import sys

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    HAS_MCP = True
except ImportError:
    HAS_MCP = False


def create_server() -> "Server":
    if not HAS_MCP:
        print("MCP SDK 未安装。安装: pip install mcp", file=sys.stderr)
        sys.exit(1)

    server = Server("souwen")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
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
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
