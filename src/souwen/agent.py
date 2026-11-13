"""Agent-facing facade: two actions (``search`` / ``fetch``) over the runtime.

Every entry point — MCP tools, the flat HTTP API, the CLI, and the package
root — goes through :class:`AgentRuntime`, so the same request yields the
same result regardless of entry. Built lazily on first use for library
callers; the server build wires its own instance explicitly.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from souwen.config import SouWenConfig, get_config
from souwen.modules.fetch.application.reader import (
    DEFAULT_MAX_CHARS,
    FetchReaderService,
    FetchPage,
    format_fetch_error,
    format_fetch_page,
)
from souwen.modules.search.application.projection import (
    CompactSearchSummary,
    format_search_error,
    format_search_summary,
    project_search_page,
)
from souwen.platform.provider_spi import ProviderError
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderRef,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.server.v2_runtime import TargetRuntime, build_target_runtime

_AGENT_EXECUTION_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class AgentSourceStatus:
    """One provider in the ``/sources`` listing."""

    id: str
    kind: str
    domain: str | None
    availability: str
    reason: str


class AgentRuntime:
    """Own the target runtime plus the fetch reader cache for agent calls."""

    def __init__(self, runtime: TargetRuntime, config: SouWenConfig | None = None) -> None:
        from souwen.server.v2_runtime import search_domains_by_provider

        self._runtime = runtime
        self._config = config or get_config()
        self._domains_by_provider = search_domains_by_provider()
        self._reader = FetchReaderService(runtime.services.fetch)
        self._closed = False

    def _context(self) -> RequestContext:
        from souwen.common_runtime.observability import get_request_id

        return RequestContext(request_id=get_request_id())

    async def search(
        self,
        query: str,
        *,
        domain: str = "web",
        limit: int = 8,
        providers: tuple[str, ...] | None = None,
    ) -> CompactSearchSummary:
        request = SearchRequest(
            query=query,
            domains=(domain,),
            page=SearchPageRequest(limit=limit),
            providers=(
                tuple(ProviderRef(id=provider_id, kind="search") for provider_id in providers)
                if providers is not None
                else None
            ),
        )
        page = await self._runtime.services.search.search(
            request,
            self._context(),
            ExecutionContext.with_timeout(_AGENT_EXECUTION_TIMEOUT_SECONDS),
        )
        return project_search_page(page)

    async def fetch(
        self,
        url: str,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        start: int = 0,
    ) -> FetchPage:
        return await self._reader.read(
            url,
            max_chars=max_chars,
            start=start,
            context=self._context(),
            execution=ExecutionContext.with_timeout(_AGENT_EXECUTION_TIMEOUT_SECONDS),
        )

    def sources(self) -> tuple[AgentSourceStatus, ...]:
        items = []
        for item in self._runtime.services.provider_items:
            items.append(
                AgentSourceStatus(
                    id=item.provider,
                    kind=item.capabilities[0],
                    domain=self._domains_by_provider.get(item.provider),
                    availability=item.availability,
                    reason=item.reason,
                )
            )
        return tuple(items)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._runtime.close()


_instance: AgentRuntime | None = None
_instance_lock = threading.Lock()


def get_agent_runtime() -> AgentRuntime:
    """Lazily build the process-wide agent runtime for library callers."""

    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AgentRuntime(build_target_runtime(get_config()))
        return _instance


async def search(
    query: str,
    domain: str = "web",
    limit: int = 8,
) -> str:
    """Search free sources in one domain and return the compact text form."""

    runtime = get_agent_runtime()
    try:
        summary = await runtime.search(query, domain=domain, limit=limit)
    except Exception as exc:
        return _safe_failure(exc, format_search_error)
    return format_search_summary(summary)


async def fetch(
    url: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    start: int = 0,
) -> str:
    """Fetch one URL and return one bounded page of its text content."""

    runtime = get_agent_runtime()
    try:
        page = await runtime.fetch(url, max_chars=max_chars, start=start)
    except Exception as exc:
        return _safe_failure(exc, format_fetch_error)
    return format_fetch_page(page)


def _safe_failure(exc: Exception, formatter) -> str:
    if isinstance(exc, ProviderError):
        return formatter(exc)
    return f"Request failed ({type(exc).__name__}). To proceed: retry, or narrow the request."


__all__ = ["AgentRuntime", "AgentSourceStatus", "fetch", "get_agent_runtime", "search"]
