"""Native Playwright execution with per-target host pinning and bounded output."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable, Protocol
from urllib.parse import urlparse

from souwen.common_runtime.security import ResolvedFetchTarget, resolve_fetch_target_async
from souwen.core.browser_pool import BrowserPoolKey, PlaywrightBrowserPool

from .protocol import WorkerFetchItem, WorkerFetchRequest


ResolveTarget = Callable[[str], Awaitable[tuple[ResolvedFetchTarget | None, str]]]


class BrowserPool(Protocol):
    """Minimum pool surface needed by one isolated Worker execution."""

    @property
    def started(self) -> bool: ...

    def page(self, **kwargs): ...

    async def close(self) -> None: ...


BrowserPoolFactory = Callable[[BrowserPoolKey], BrowserPool]


class BrowserExecutionError(RuntimeError):
    """Stable Worker-local failure without raw browser details."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def _default_pool_factory(key: BrowserPoolKey) -> PlaywrightBrowserPool:
    return PlaywrightBrowserPool(key, max_pages=2)


class PlaywrightBrowserExecutor:
    """Execute one browser target in a transient host-pinned browser pool."""

    def __init__(
        self,
        *,
        resolver: ResolveTarget = resolve_fetch_target_async,
        pool_factory: BrowserPoolFactory = _default_pool_factory,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._resolver = resolver
        self._pool_factory = pool_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._pool = self._pool_factory(BrowserPoolKey())
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready and self._pool.started

    async def initialize(self) -> None:
        """Prove that Chromium can create and close an isolated context without network."""
        try:
            async with self._pool.page(accept_downloads=False, service_workers="block"):
                pass
            self._ready = True
        except asyncio.CancelledError:
            raise
        except Exception:
            self._ready = False
            raise BrowserExecutionError("worker_not_ready", retryable=True) from None

    async def execute(
        self,
        request: WorkerFetchRequest,
        *,
        timeout_seconds: float,
    ) -> WorkerFetchItem:
        if timeout_seconds <= 0:
            raise BrowserExecutionError("worker_timeout", retryable=True)

        target_url = str(request.target)
        resolved, _reason = await self._resolver(target_url)
        if resolved is None:
            raise BrowserExecutionError("policy_blocked")

        from .network_proxy import PinnedLoopbackProxy

        proxy = PinnedLoopbackProxy(
            target_url=target_url,
            resolver=self._resolver,
        )
        await proxy.start()
        policy_blocked = False

        async def enforce_policy(route, browser_request) -> None:
            nonlocal policy_blocked
            request_url = str(browser_request.url)
            parsed = urlparse(request_url)
            if parsed.scheme in {"data", "blob", "about"}:
                await route.continue_()
                return
            try:
                current, _current_reason = await self._resolver(request_url)
                if current is None:
                    raise BrowserExecutionError("policy_blocked")
                proxy.allow_url(request_url)
            except BrowserExecutionError:
                policy_blocked = True
                await route.abort("blockedbyclient")
                return
            await route.continue_()

        async def execute_page() -> WorkerFetchItem:
            async with self._pool.page(
                accept_downloads=False,
                service_workers="block",
                proxy=proxy.url,
            ) as page:
                await page.route("**/*", enforce_policy)
                remaining_ms = max(1, int(timeout_seconds * 1000))
                try:
                    response = await page.goto(
                        target_url,
                        wait_until="domcontentloaded",
                        timeout=remaining_ms,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if policy_blocked:
                        raise BrowserExecutionError("policy_blocked") from None
                    raise BrowserExecutionError("worker_unavailable", retryable=True) from None
                if policy_blocked:
                    raise BrowserExecutionError("policy_blocked")
                if response is None or int(response.status) >= 400:
                    raise BrowserExecutionError("worker_unavailable", retryable=True)

                final_url = str(page.url)
                final_target, _final_reason = await self._resolver(final_url)
                if final_target is None:
                    raise BrowserExecutionError("policy_blocked")

                content = (await page.locator("body").inner_text()).strip()
                if not content:
                    raise BrowserExecutionError("empty_content")
                truncated = len(content) > request.max_code_points
                normalized = content[: request.max_code_points]
                headers = await response.all_headers()
                raw_content_type = headers.get("content-type", "text/html")
                media_type, _, parameters = raw_content_type.partition(";")
                charset = None
                for parameter in parameters.split(";"):
                    key, separator, value = parameter.strip().partition("=")
                    if separator and key.lower() == "charset":
                        charset = value.strip().strip('"') or None
                        break
                retrieved_at = self._clock()
                if retrieved_at.tzinfo is None:
                    raise BrowserExecutionError("worker_unavailable")
                return WorkerFetchItem(
                    final_url=final_url,
                    title=(await page.title()).strip() or None,
                    content=normalized,
                    media_type=media_type.strip().lower() or "text/html",
                    charset=charset,
                    retrieved_at=retrieved_at,
                    truncated=truncated,
                    content_length=len(normalized.encode("utf-8")),
                    quality="low" if len(normalized.strip()) <= 63 else "high",
                )

        try:
            return await asyncio.wait_for(execute_page(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            raise BrowserExecutionError("worker_timeout", retryable=True) from None
        finally:
            await proxy.close()

    async def close(self) -> None:
        self._ready = False
        await self._pool.close()


__all__ = ["BrowserExecutionError", "PlaywrightBrowserExecutor"]
