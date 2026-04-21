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

    fetch_paper_details
        - 按 ID 或 DOI 获取单篇论文详情
        - 参数：paper_id (SS Paper ID / DOI:xxx / ARXIV:xxx), source (可选，默认 "semantic_scholar")
        - 返回：PaperResult (JSON)，含 TL;DR、OA 状态、PDF 链接等

    search_by_topic
        - 带年份范围过滤的主题搜索
        - 参数：topic, year_start (可选), year_end (可选), sources (可选), limit (可选，默认 10)
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

# ── 年份范围过滤用常量 ───────────────────────────────────────
# arXiv 日期过滤后缀
_MONTH_START = "-01-01"  # 年份起始月日（YYYY-01-01）
_MONTH_END = "-12-31"  # 年份结束月日（YYYY-12-31）
# Semantic Scholar year 过滤占位值（未指定端点时）
_YEAR_MIN = "0001"
_YEAR_MAX = "9999"


def create_server() -> "Server":
    """创建并配置 MCP 服务器 — 注册工具和处理函数

    工具列表：
    1. search_papers - 论文搜索
    2. fetch_paper_details - 按 ID/DOI 获取论文详情
    3. search_by_topic - 带年份范围的主题搜索
    4. search_patents - 专利搜索
    5. web_search - 网页搜索
    6. get_status - 数据源健康检查

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
                name="fetch_paper_details",
                description=(
                    "按 Paper ID 或 DOI 获取单篇论文详情。"
                    "Semantic Scholar 支持 Paper ID、DOI:xxx、ARXIV:xxx 格式；"
                    "Crossref 接受标准 DOI（如 10.1038/s41586-021-03819-2）。"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "paper_id": {
                            "type": "string",
                            "description": (
                                "论文标识符：Semantic Scholar Paper ID、"
                                "DOI（如 DOI:10.1038/xxx 或直接 10.1038/xxx）、"
                                "arXiv ID（如 ARXIV:2301.00001）"
                            ),
                        },
                        "source": {
                            "type": "string",
                            "enum": ["semantic_scholar", "crossref"],
                            "default": "semantic_scholar",
                            "description": "数据源，默认 semantic_scholar",
                        },
                    },
                    "required": ["paper_id"],
                },
            ),
            Tool(
                name="search_by_topic",
                description=(
                    "按主题搜索论文，支持年份范围过滤。"
                    "可指定 year_start / year_end 限定发表时间段，"
                    "适合跟踪特定领域的最新或历史研究。"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "搜索主题/关键词"},
                        "year_start": {
                            "type": "integer",
                            "description": "起始年份（含），如 2020",
                        },
                        "year_end": {
                            "type": "integer",
                            "description": "结束年份（含），如 2024",
                        },
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "数据源列表，默认 arxiv,semantic_scholar,crossref",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 10,
                            "description": "每源返回数量",
                        },
                    },
                    "required": ["topic"],
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
        """工具调用处理器 — 委托给 handle_tool_call，封装为 MCP TextContent。

        参数：
            name: 工具名称
            arguments: 工具参数字典

        Returns:
            list[TextContent]：单个文本内容项，包含 JSON 结果
        """
        try:
            result = await handle_tool_call(name, arguments)
            text = (
                json.dumps(result, ensure_ascii=False, indent=2)
                if isinstance(result, (dict, list))
                else str(result)
            )
            return [TextContent(type="text", text=text)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]

    return server


async def handle_tool_call(name: str, arguments: dict):
    """工具调用业务逻辑 — 独立于 MCP SDK，可直接测试。

    参数：
        name: 工具名称（search_papers、fetch_paper_details、search_by_topic、
              search_patents、web_search、get_status）
        arguments: 工具参数字典

    Returns:
        JSON 可序列化的 Python 对象（dict / list / str）

    说明：
        单个数据源的失败（search_by_topic）被捕获后以错误条目形式附加到结果，
        不影响其余源。其余工具的异常向上抛出，由调用方处理。
    """
    if name == "search_papers":
        from souwen.search import search_papers

        sources = arguments.get("sources", ["openalex", "arxiv", "crossref"])
        limit = arguments.get("limit", 5)
        responses = await search_papers(arguments["query"], sources=sources, per_page=limit)
        return [r.model_dump(mode="json") for r in responses]

    if name == "fetch_paper_details":
        from souwen.paper.semantic_scholar import SemanticScholarClient
        from souwen.paper.crossref import CrossrefClient

        paper_id: str = arguments["paper_id"]
        source: str = arguments.get("source", "semantic_scholar")

        if source == "semantic_scholar":
            async with SemanticScholarClient() as client:
                paper = await client.get_paper(paper_id)
            return paper.model_dump(mode="json")
        if source == "crossref":
            async with CrossrefClient() as client:
                paper = await client.get_by_doi(paper_id)
            return paper.model_dump(mode="json")
        return {
            "error": f"不支持的数据源: {source!r}",
            "supported_sources": ["semantic_scholar", "crossref"],
        }

    if name == "search_by_topic":
        from souwen.paper.arxiv import ArxivClient
        from souwen.paper.semantic_scholar import SemanticScholarClient
        from souwen.paper.crossref import CrossrefClient

        topic: str = arguments["topic"]
        year_start: int | None = arguments.get("year_start")
        year_end: int | None = arguments.get("year_end")
        limit = arguments.get("limit", 10)
        sources = arguments.get("sources", ["arxiv", "semantic_scholar", "crossref"])

        all_papers: list = []

        for src in sources:
            try:
                if src == "arxiv":
                    date_from = f"{year_start}{_MONTH_START}" if year_start else None
                    date_to = f"{year_end}{_MONTH_END}" if year_end else None
                    async with ArxivClient() as client:
                        resp = await client.search(
                            topic,
                            max_results=limit,
                            date_from=date_from,
                            date_to=date_to,
                        )
                    all_papers.extend(p.model_dump(mode="json") for p in resp.results)
                elif src == "semantic_scholar":
                    # Semantic Scholar 支持 year=YYYY-YYYY 过滤
                    query = topic
                    if year_start or year_end:
                        y_start = str(year_start) if year_start else _YEAR_MIN
                        y_end = str(year_end) if year_end else _YEAR_MAX
                        query = f"{topic} year:{y_start}-{y_end}"
                    async with SemanticScholarClient() as client:
                        resp = await client.search(query, limit=limit)
                    all_papers.extend(p.model_dump(mode="json") for p in resp.results)
                elif src == "crossref":
                    filters: dict[str, str] = {}
                    if year_start:
                        filters["from-pub-date"] = str(year_start)
                    if year_end:
                        filters["until-pub-date"] = str(year_end)
                    async with CrossrefClient() as client:
                        resp = await client.search(
                            topic,
                            filters=filters if filters else None,
                            rows=limit,
                        )
                    all_papers.extend(p.model_dump(mode="json") for p in resp.results)
            except Exception as src_exc:
                # 单个源失败不阻止其他源继续
                all_papers.append(
                    {"source": src, "error": f"{type(src_exc).__name__}: {src_exc}"}
                )

        return all_papers

    if name == "search_patents":
        from souwen.search import search_patents

        sources = arguments.get("sources", ["google_patents"])
        limit = arguments.get("limit", 5)
        responses = await search_patents(
            arguments["query"], sources=sources, per_page=limit
        )
        return [r.model_dump(mode="json") for r in responses]

    if name == "web_search":
        from souwen.web.search import web_search

        engines = arguments.get("engines")
        limit = arguments.get("limit", 10)
        response = await web_search(
            arguments["query"], engines=engines, max_results_per_engine=limit
        )
        return response.model_dump(mode="json")

    if name == "get_status":
        from souwen.doctor import check_all, format_report

        results = check_all()
        return format_report(results)

    return f"Unknown tool: {name}"


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
