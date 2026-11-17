"""MCP server exposing exactly the ``search`` and ``fetch`` tools (SPEC 2.1).

Source status travels as the ``souwen://sources`` resource, not as a tool.
Built on the official ``mcp`` SDK's FastMCP; stdio via ``souwen mcp``, and
streamable HTTP by mounting :meth:`build_mcp_server` result under the FastAPI
app (see ``server/app.py``; the session manager must run in the app lifespan).
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from souwen.agent import AgentRuntime
from souwen.config.loader import get_config
from souwen.config.models import SouWenConfig
from souwen.modules.fetch.application.reader import (
    DEFAULT_MAX_CHARS,
    format_fetch_error,
    format_fetch_page,
)
from souwen.modules.search.application.projection import (
    format_search_error,
    format_search_summary,
)
from souwen.platform.provider_spi import ProviderError

_SEARCH_TOOL_DESCRIPTION = """Search free web sources for a query.

Pick the domain that matches the question:
- web: general web pages (default)
- news: current events
- paper: academic papers, preprints, datasets (adds year/authors)
- patent: patent documents
- book: books and book catalogs
- code: code and developer Q&A
- community: forum and community discussions (mostly Chinese)
- wiki: encyclopedia articles
- images: image search
- videos: video search

The tool runs several free sources with automatic fallback; you do not pick
sources. Results are numbered: title, URL, snippet.
"""

_FETCH_TOOL_DESCRIPTION = """Fetch one URL and return its main content as text.

Long pages are truncated; the last line names the ``start`` value to pass on
the next call to continue reading from where this page stopped. Repeated
reads of the same URL reuse a short-lived cache, so continuation is cheap.
"""

_MCP_INSTRUCTIONS = (
    "SouWen gives agents two actions over free sources: search and fetch. "
    "Search first, then fetch the promising URLs. When a fetch is truncated, "
    "continue with the reported start value instead of refetching."
)


def _resolve_transport_security(config: SouWenConfig) -> TransportSecuritySettings:
    """合成 /mcp 的 Host/Origin 允许列表（保持 SDK 的 DNS-rebinding 防护开启）。

    默认放行两类主机：

    - loopback（``127.0.0.1`` / ``localhost`` / ``::1``，任意端口）：本地 HTTP
      客户端与容器内探针的默认用法；
    - 平台注入的 ``SPACE_HOST``（裸主机名，如 ``<space>.hf.space``）：HF Spaces
      官方运行时变量，只在 Space 里存在，值由平台控制，不来自请求头。

    显式配置 ``mcp_allowed_hosts`` / ``mcp_allowed_origins`` 时完全取代默认
    hosts（loopback 也不例外，测试里用显式 ``testserver`` 就是这种情况）；
    origins 默认为空列表——Origin 缺失的请求本来就放行，带 Origin 的浏览器
    场景需要显式列出。禁止从请求的 Host/Origin/forwarded 头动态扩充。
    """

    hosts: list[str]
    if config.mcp_allowed_hosts:
        hosts = list(config.mcp_allowed_hosts)
    else:
        hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
        space_host = os.environ.get("SPACE_HOST", "").strip()
        # 只接受形如裸主机名的值（无 scheme、无路径、非通配）；逐字符校验
        # 而不是正则，避免把任意输入放进来。
        if (
            space_host
            and all(ch.isalnum() or ch in "-._" for ch in space_host)
            and "." in space_host
        ):
            hosts.append(space_host)

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=list(config.mcp_allowed_origins),
    )


def build_mcp_server(runtime: AgentRuntime, config: SouWenConfig | None = None) -> FastMCP:
    # FastMCP 默认 host="127.0.0.1"，mcp>=1.30 据此自动开启 DNS-rebinding 防护并把
    # allowed_hosts 限定为 localhost。反代后 Host 是部署域名（如 *.hf.space），POST /mcp
    # 曾拿到 421 Invalid Host header。这里不整体关闭防护（那会放行任意 Host/Origin），
    # 而是按配置合成精确的允许列表：loopback + SPACE_HOST（HF 平台变量）或用户显式
    # 配置。鉴权仍由 McpAuthMiddleware（fail-closed）独立承担，三层语义互不替代。
    mcp: FastMCP = FastMCP(
        "souwen",
        instructions=_MCP_INSTRUCTIONS,
        transport_security=_resolve_transport_security(
            config if config is not None else get_config()
        ),
    )

    @mcp.tool(description=_SEARCH_TOOL_DESCRIPTION)
    async def search(query: str, domain: str = "web", limit: int = 8) -> str:
        """Search free sources in one domain; returns numbered results as text."""
        try:
            summary = await runtime.search(query, domain=domain, limit=limit)
        except ProviderError as exc:
            return format_search_error(exc)
        except Exception as exc:
            return f"Search failed ({type(exc).__name__}). To proceed: retry or narrow the query."
        return format_search_summary(summary)

    @mcp.tool(description=_FETCH_TOOL_DESCRIPTION)
    async def fetch(url: str, max_chars: int = DEFAULT_MAX_CHARS, start: int = 0) -> str:
        """Fetch one URL; returns a metadata line, the content slice, and how to continue."""
        try:
            page = await runtime.fetch(url, max_chars=max_chars, start=start)
        except ProviderError as exc:
            return format_fetch_error(exc)
        except Exception as exc:
            return f"Fetch failed ({type(exc).__name__}). To proceed: retry or try another URL."
        return format_fetch_page(page)

    @mcp.resource("souwen://sources")
    def sources() -> str:
        """Source list with domain and availability."""
        lines = [
            f"{item.id}: kind={item.kind} domain={item.domain or '-'} "
            f"availability={item.availability} reason={item.reason}"
            for item in runtime.sources()
        ]
        return "\n".join(lines)

    return mcp


__all__ = ["build_mcp_server"]
