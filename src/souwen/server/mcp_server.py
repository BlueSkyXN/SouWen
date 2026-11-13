"""MCP server exposing exactly the ``search`` and ``fetch`` tools (SPEC 2.1).

Source status travels as the ``souwen://sources`` resource, not as a tool.
Built on the official ``mcp`` SDK's FastMCP; stdio via ``souwen mcp``, and
streamable HTTP by mounting :meth:`build_mcp_server` result under the FastAPI
app (see ``server/app.py``; the session manager must run in the app lifespan).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from souwen.agent import AgentRuntime
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


def build_mcp_server(runtime: AgentRuntime) -> FastMCP:
    mcp: FastMCP = FastMCP("souwen", instructions=_MCP_INSTRUCTIONS)

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
