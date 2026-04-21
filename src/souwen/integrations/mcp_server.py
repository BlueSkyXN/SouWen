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
        - 支持：OpenAlex, Semantic Scholar, Crossref, arXiv, DBLP, CORE, PubMed, HuggingFace Papers,
                Europe PMC, PMC, DOAJ, Zenodo, HAL, OpenAIRE, IACR
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

    fetch_content
        - 抓取网页内容
        - 参数：urls (list), provider (可选，默认 builtin)
        - 返回：抓取结果 (JSON)

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

from souwen.integrations._tools_bilibili import (
    dispatch_bilibili_tool,
    get_bilibili_tools,
    is_bilibili_tool,
)


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
                    "Crossref, arXiv, DBLP, CORE, PubMed, Unpaywall, HuggingFace Papers, "
                    "Europe PMC, PMC, DOAJ, Zenodo, HAL, OpenAIRE, IACR。"
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
            *get_bilibili_tools(),
            Tool(
                name="fetch_content",
                description="获取网页内容。支持 URL 直接抓取，使用 SouWen 内置提取器（零配置）。支持 CSS 选择器提取指定元素、分页续读。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要抓取的 URL 列表",
                        },
                        "provider": {
                            "type": "string",
                            "default": "builtin",
                            "description": "内容提取提供者，默认 builtin（零配置）",
                        },
                        "selector": {
                            "type": "string",
                            "description": "CSS 选择器，仅提取匹配元素内容（仅 builtin 支持）",
                        },
                        "start_index": {
                            "type": "integer",
                            "default": 0,
                            "description": "内容起始切片位置（用于分页续读）",
                        },
                        "max_length": {
                            "type": "integer",
                            "description": "内容最大长度，超出则截断并返回 next_start_index",
                        },
                        "respect_robots_txt": {
                            "type": "boolean",
                            "default": False,
                            "description": "是否遵守 robots.txt（仅 builtin 支持）",
                        },
                    },
                    "required": ["urls"],
                },
            ),
            Tool(
                name="extract_links",
                description="提取网页中的所有链接。返回去重、SSRF 过滤后的链接列表（URL + 锚文本）。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "目标页面 URL",
                        },
                        "base_url_filter": {
                            "type": "string",
                            "description": "URL 前缀过滤（仅返回以此开头的链接）",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 100,
                            "description": "最大返回链接数（1-1000）",
                        },
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="parse_sitemap",
                description="解析网站 sitemap.xml，提取 URL 列表。支持 sitemap index 递归、gzip 压缩、robots.txt 自动发现。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Sitemap URL 或站点根 URL",
                        },
                        "discover": {
                            "type": "boolean",
                            "default": False,
                            "description": "自动从 robots.txt 发现 sitemap",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 1000,
                            "description": "最大返回条目数",
                        },
                    },
                    "required": ["url"],
                },
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

            elif is_bilibili_tool(name):
                result = await dispatch_bilibili_tool(name, arguments)

            elif name == "fetch_content":
                from souwen.web.fetch import fetch_content

                urls = arguments["urls"]
                provider = arguments.get("provider", "builtin")
                selector = arguments.get("selector")
                start_index = arguments.get("start_index", 0)
                max_length = arguments.get("max_length")
                respect_robots_txt = arguments.get("respect_robots_txt", False)
                response = await fetch_content(
                    urls=urls,
                    providers=[provider],
                    selector=selector,
                    start_index=start_index,
                    max_length=max_length,
                    respect_robots_txt=respect_robots_txt,
                )
                result = response.model_dump(mode="json")

            elif name == "extract_links":
                from souwen.web.links import extract_links

                result_obj = await extract_links(
                    url=arguments["url"],
                    base_url_filter=arguments.get("base_url_filter"),
                    limit=arguments.get("limit", 100),
                )
                result = result_obj.model_dump(mode="json")

            elif name == "parse_sitemap":
                from souwen.web.sitemap import discover_sitemap, parse_sitemap

                sitemap_url = arguments["url"]
                do_discover = arguments.get("discover", False)
                limit = arguments.get("limit", 1000)
                if do_discover:
                    result_obj = await discover_sitemap(sitemap_url, max_entries=limit)
                else:
                    result_obj = await parse_sitemap(sitemap_url, max_entries=limit)
                result = result_obj.model_dump(mode="json")

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
