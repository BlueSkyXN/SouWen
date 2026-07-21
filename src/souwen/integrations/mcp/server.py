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
        - 参数：urls (list), provider/providers (可选，默认 builtin), strategy (可选，默认 fallback)
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
import logging
from typing import cast

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    HAS_MCP = True
except ImportError:
    HAS_MCP = False

from souwen.core.redaction import redact_secret_text
from souwen.integrations.mcp.tools.bilibili import (
    dispatch_bilibili_tool,
    get_bilibili_tools,
    is_bilibili_tool,
)
from souwen.registry import defaults_for, get as _registry_get

logger = logging.getLogger("souwen.integrations.mcp.server")

_MCP_PLUGINS_BOOTSTRAPPED = False


def _bootstrap_plugins() -> None:
    """加载配置可见的外部插件，确保 MCP stdio 独立启动时也能看到插件源。"""
    global _MCP_PLUGINS_BOOTSTRAPPED
    if _MCP_PLUGINS_BOOTSTRAPPED:
        return

    try:
        from souwen.config import get_config
        from souwen.plugin import ensure_plugins_loaded

        result = ensure_plugins_loaded(get_config())
        if result.errors:
            logger.warning("MCP 插件加载完成，错误 %d 个", len(result.errors))
    except Exception:  # noqa: BLE001 - MCP 不应因第三方插件失败而无法启动
        logger.warning("MCP 插件初始化失败，继续使用已注册源。", exc_info=True)
    finally:
        _MCP_PLUGINS_BOOTSTRAPPED = True


def _default_paper_sources_label() -> str:
    return _default_source_names_label("paper", "search")


def _default_book_sources_label() -> str:
    return _default_source_names_label("book", "search")


def _default_patent_sources_label() -> str:
    return _default_source_names_label("patent", "search")


def _default_web_engines_label() -> str:
    return _default_source_names_label("web", "search")


def _default_source_names_label(domain: str, capability: str) -> str:
    _bootstrap_plugins()
    names = defaults_for(domain, capability)
    return ",".join(_edition_allowed_source_names(names))


def _edition_allowed_source_names(names: list[str]) -> list[str]:
    """Filter source/default labels to what the current edition can actually run."""

    from souwen.config import get_config
    from souwen.editions import source_policy

    edition = get_config().edition
    allowed: list[str] = []
    for name in names:
        adapter = _registry_get(name)
        if adapter is None:
            continue
        if source_policy(adapter, edition).available:
            allowed.append(name)
    return allowed


def _fetch_provider_names() -> list[str]:
    """返回当前 edition 声明的 fetch provider 名称，默认源优先显示。"""
    from souwen.config import get_config
    from souwen.feature_matrix import fetch_provider_runtime_projection

    _bootstrap_plugins()
    names = [
        item.name
        for item in fetch_provider_runtime_projection(get_config().edition)
        if item.edition_available
    ]
    if "builtin" not in names:
        return names
    return ["builtin", *(name for name in names if name != "builtin")]


def _fetch_provider_projection() -> dict[str, object]:
    """Return the MCP schema projection without confusing policy with runtime."""
    from souwen.config import get_config
    from souwen.feature_matrix import fetch_provider_runtime_projection

    _bootstrap_plugins()
    statuses = list(fetch_provider_runtime_projection(get_config().edition))
    statuses.sort(key=lambda item: (item.name != "builtin", item.name))
    providers = [
        {
            "name": item.name,
            "min_edition": item.min_edition,
            "edition_available": item.edition_available,
            "edition_reason": item.edition_reason,
            "runtime_available": item.runtime_available,
            "runtime_reason": item.runtime_reason,
            "available": item.available,
        }
        for item in statuses
    ]
    return {
        "declared": [item["name"] for item in providers if item["edition_available"]],
        "available": [item["name"] for item in providers if item["available"]],
        "unavailable": [
            item
            for item in providers
            if item["edition_available"] and not item["runtime_available"]
        ],
        "upgrade_required": [item for item in providers if not item["edition_available"]],
        "providers": providers,
    }


def _fetch_provider_projection_label(projection: dict[str, object]) -> str:
    """Render the truthful subset of the provider projection for tool descriptions."""

    declared = " / ".join(cast(list[str], projection["declared"])) or "无"
    available = " / ".join(cast(list[str], projection["available"])) or "无"
    unavailable_items = cast(list[dict[str, object]], projection["unavailable"])
    unavailable = ""
    if unavailable_items:
        details = "; ".join(
            f"{item['name']}（{item['runtime_reason']}）" for item in unavailable_items
        )
        unavailable = f"；当前缺运行时依赖：{details}"
    return f"当前 edition 声明：{declared}；当前 runtime 可导入：{available}{unavailable}"


def _string_list_arg(value: object, *, name: str) -> list[str]:
    """Normalize MCP string-or-list arguments into a string list."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list | tuple):
        items = list(value)
    else:
        raise ValueError(f"{name} 必须是字符串或字符串列表")

    if not all(isinstance(item, str) and item.strip() for item in items):
        raise ValueError(f"{name} 必须是非空字符串或非空字符串列表")
    return items


def _normalize_fetch_tool_urls(value: object) -> list[str]:
    urls = _string_list_arg(value, name="urls")
    if not urls:
        raise ValueError("urls 至少需要一个 URL")
    return urls


def _normalize_fetch_tool_providers(provider: object, providers: object) -> list[str]:
    selected = _string_list_arg(providers, name="providers")
    if selected:
        return selected
    fallback_provider = "builtin" if provider is None else provider
    selected = _string_list_arg(fallback_provider, name="provider")
    return selected or ["builtin"]


def _string_or_string_array_schema(description: str) -> dict[str, object]:
    """Return JSON Schema for MCP arguments accepting one string or string list."""
    return {
        "oneOf": [
            {"type": "string"},
            {"type": "array", "items": {"type": "string"}},
        ],
        "description": description,
    }


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

    _bootstrap_plugins()
    server = Server("souwen")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """返回 MCP 工具清单 — 由 MCP SDK 在客户端连接时调用"""
        fetch_provider_projection = _fetch_provider_projection()
        fetch_provider_projection_label = _fetch_provider_projection_label(
            fetch_provider_projection
        )
        book_sources_label = _default_book_sources_label()
        patent_sources_label = _default_patent_sources_label()
        web_engines_label = _default_web_engines_label()
        return [
            Tool(
                name="search_books",
                description="搜索 work 级图书书目；资源链接只表达上游访问状态，不执行借阅或下载。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "sources": _string_or_string_array_schema(
                            f"数据源或数据源列表，默认 {book_sources_label}"
                        ),
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
                        "sources": _string_or_string_array_schema(
                            f"数据源或数据源列表，默认 {_default_paper_sources_label()}"
                        ),
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
                        "sources": _string_or_string_array_schema(
                            f"数据源或数据源列表，默认 {patent_sources_label}"
                        ),
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
                description=f"网页搜索。默认 {web_engines_label}。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "engines": _string_or_string_array_schema(
                            f"引擎或引擎列表，默认 {web_engines_label}"
                        ),
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
                name="citation_count",
                description="查询 DOI、PMID 或 OMID 的 OpenCitations 被引计数。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "identifier": {"type": "string", "description": "DOI、PMID 或 OMID"}
                    },
                    "required": ["identifier"],
                },
            ),
            Tool(
                name="citation_incoming",
                description="查询 OpenCitations 被引边；max_edges 是本地输出上限，不是 upstream pagination。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "identifier": {"type": "string", "description": "DOI、PMID 或 OMID"},
                        "max_edges": {
                            "type": "integer",
                            "default": 100,
                            "minimum": 1,
                            "maximum": 1000,
                        },
                    },
                    "required": ["identifier"],
                },
            ),
            Tool(
                name="citation_references",
                description="查询 OpenCitations 参考文献边；max_edges 是本地输出上限，不是 upstream pagination。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "identifier": {"type": "string", "description": "DOI、PMID 或 OMID"},
                        "max_edges": {
                            "type": "integer",
                            "default": 100,
                            "minimum": 1,
                            "maximum": 1000,
                        },
                    },
                    "required": ["identifier"],
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
                description=(
                    "获取网页内容。支持 URL 直接抓取，可通过 provider/providers 选择已注册 "
                    "fetch provider（默认 builtin）。"
                    f"{fetch_provider_projection_label}。"
                    "strategy 支持 fallback 或 fanout。"
                    "支持 CSS 选择器提取指定元素、分页续读。"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "urls": _string_or_string_array_schema("要抓取的 URL 或 URL 列表"),
                        "provider": {
                            "type": "string",
                            "default": "builtin",
                            "description": (
                                "兼容单内容提取提供者，默认 builtin（零配置）；"
                                f"{fetch_provider_projection_label}"
                            ),
                            "x-souwen-provider-projection": fetch_provider_projection,
                        },
                        "providers": {
                            **_string_or_string_array_schema(
                                "内容提取提供者或提供者列表；提供时优先于 provider。"
                                f"{fetch_provider_projection_label}"
                            ),
                            "x-souwen-provider-projection": fetch_provider_projection,
                        },
                        "strategy": {
                            "type": "string",
                            "enum": ["fallback", "fanout"],
                            "default": "fallback",
                            "description": "多 provider 策略：fallback 按 URL 补失败项，fanout 返回全部 provider 结果",
                        },
                        "selector": {
                            "type": "string",
                            "description": "CSS 选择器，仅提取匹配元素内容（builtin / scrapling 支持）",
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
                            "description": "是否遵守 robots.txt（provider 支持时生效）",
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
            if name == "search_books":
                from souwen.search import search_books

                sources = _string_list_arg(arguments.get("sources"), name="sources") or None
                limit = arguments.get("limit", 5)
                responses = await search_books(arguments["query"], sources=sources, per_page=limit)
                result = [response.model_dump(mode="json") for response in responses]

            elif name == "search_papers":
                from souwen.search import search_papers

                sources = _string_list_arg(arguments.get("sources"), name="sources") or None
                limit = arguments.get("limit", 5)
                responses = await search_papers(arguments["query"], sources=sources, per_page=limit)
                result = [r.model_dump(mode="json") for r in responses]

            elif name == "search_patents":
                from souwen.search import search_patents

                sources = _string_list_arg(arguments.get("sources"), name="sources") or None
                limit = arguments.get("limit", 5)
                responses = await search_patents(
                    arguments["query"], sources=sources, per_page=limit
                )
                result = [r.model_dump(mode="json") for r in responses]

            elif name == "web_search":
                from souwen.web.search import web_search

                engines = _string_list_arg(arguments.get("engines"), name="engines") or None
                limit = arguments.get("limit", 10)
                response = await web_search(
                    arguments["query"], engines=engines, max_results_per_engine=limit
                )
                result = response.model_dump(mode="json")

            elif name == "citation_count":
                from souwen.citations import get_citation_count

                result = (await get_citation_count(arguments["identifier"])).model_dump(mode="json")

            elif name == "citation_incoming":
                from souwen.citations import get_incoming_citations

                result = (
                    await get_incoming_citations(
                        arguments["identifier"], max_edges=arguments.get("max_edges", 100)
                    )
                ).model_dump(mode="json")

            elif name == "citation_references":
                from souwen.citations import get_references

                result = (
                    await get_references(
                        arguments["identifier"], max_edges=arguments.get("max_edges", 100)
                    )
                ).model_dump(mode="json")

            elif name == "get_status":
                from souwen.doctor import check_all, format_report

                results = check_all()
                result = format_report(results)

            elif is_bilibili_tool(name):
                result = await dispatch_bilibili_tool(name, arguments)

            elif name == "fetch_content":
                from souwen.web.fetch import fetch_content

                urls = _normalize_fetch_tool_urls(arguments.get("urls"))
                provider = arguments.get("provider", "builtin")
                providers = _normalize_fetch_tool_providers(provider, arguments.get("providers"))
                strategy = arguments.get("strategy", "fallback")
                selector = arguments.get("selector")
                start_index = arguments.get("start_index", 0)
                max_length = arguments.get("max_length")
                respect_robots_txt = arguments.get("respect_robots_txt", False)
                response = await fetch_content(
                    urls=urls,
                    providers=providers,
                    strategy=strategy,
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
            detail = redact_secret_text(str(e)) or "unknown error"
            return [TextContent(type="text", text=f"Error: {type(e).__name__}: {detail}")]

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
