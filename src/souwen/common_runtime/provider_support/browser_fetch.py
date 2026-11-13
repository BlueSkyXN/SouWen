"""In-process browser acquisition over the shared Playwright pool (SPEC 5.6).

The Browser Worker subprocess, its HMAC loopback protocol, and the worker
client are gone; the acquisition logic they contained runs here instead:
every browser request is resolved through the SSRF validator before it may
proceed (route enforcement), the final URL is re-validated after navigation,
and pages are bounded by the caller's timeout. Two entry points serve both
sides of the product: ``fetch_page_content`` extracts readable text for the
fetch ladder, ``fetch_page_html`` returns raw HTML for search parsers.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

from souwen.common_runtime.security import resolve_fetch_target_async

logger = logging.getLogger("souwen.common_runtime.provider_support.browser_fetch")

_MAX_CODE_POINTS = 1_000_000


@dataclass(frozen=True, slots=True)
class BrowserPageOutcome:
    final_url: str
    title: str | None
    content: str
    media_type: str
    charset: str | None
    truncated: bool


class BrowserAcquisitionError(Exception):
    """Typed browser-level failure with a safe code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


# 每个请求各建 pool 会各自启动一个 Chromium；按代理值共享 pool 实例。
_shared_pools: dict[str | None, Any] = {}


def _shared_pool(proxy: str | None) -> Any:
    from souwen.common_runtime.provider_support.browser_pool import PlaywrightBrowserPool

    pool = _shared_pools.get(proxy)
    if pool is None:
        pool = PlaywrightBrowserPool()
        _shared_pools[proxy] = pool
    return pool


async def close_shared_pools() -> None:
    """Close cached pools at process shutdown."""

    pools = list(_shared_pools.values())
    _shared_pools.clear()
    for pool in pools:
        try:
            await pool.close()
        except Exception:
            pass


@asynccontextmanager
async def _validated_page(
    url: str, *, timeout_seconds: float, proxy: str | None
) -> AsyncIterator[Any]:
    resolved, _reason = await resolve_fetch_target_async(url)
    if resolved is None:
        raise BrowserAcquisitionError("policy_blocked")

    pool = _shared_pool(proxy)
    policy_blocked = False

    async def enforce_policy(route, browser_request) -> None:
        nonlocal policy_blocked
        request_url = str(browser_request.url)
        parsed = urlsplit(request_url)
        if parsed.scheme in {"data", "blob", "about"}:
            await route.continue_()
            return
        current, _current_reason = await resolve_fetch_target_async(request_url)
        if current is None:
            policy_blocked = True
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    async with pool.page(
        accept_downloads=False,
        service_workers="block",
        proxy=proxy,
    ) as page:
        try:
            await page.route("**/*", enforce_policy)
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=max(1, int(timeout_seconds * 1000))
            )
        except Exception as exc:
            if policy_blocked:
                raise BrowserAcquisitionError("policy_blocked") from None
            raise BrowserAcquisitionError("browser_unavailable") from exc
        if policy_blocked:
            raise BrowserAcquisitionError("policy_blocked")
        if response is None or int(response.status) >= 400:
            raise BrowserAcquisitionError("bad_status")
        final_url = str(page.url)
        final_target, _final_reason = await resolve_fetch_target_async(final_url)
        if final_target is None:
            raise BrowserAcquisitionError("policy_blocked")
        yield page, response


async def fetch_page_content(
    url: str,
    *,
    max_code_points: int = 200_000,
    timeout_seconds: float = 30.0,
    proxy: str | None = None,
) -> BrowserPageOutcome:
    """Load the page and return its readable text (fetch ladder executor)."""

    try:
        async with _validated_page(url, timeout_seconds=timeout_seconds, proxy=proxy) as (
            page,
            response,
        ):
            content = (await page.locator("body").inner_text()).strip()
            if not content:
                raise BrowserAcquisitionError("empty_content")
            truncated = len(content) > max_code_points
            normalized = content[:max_code_points]
            headers = await response.all_headers()
            raw_content_type = headers.get("content-type", "text/html")
            media_type, _, parameters = raw_content_type.partition(";")
            charset = None
            for parameter in parameters.split(";"):
                key, separator, value = parameter.strip().partition("=")
                if separator and key.lower() == "charset":
                    charset = value.strip().strip('"') or None
                    break
            return BrowserPageOutcome(
                final_url=str(page.url),
                title=(await page.title()).strip() or None,
                content=normalized,
                media_type=media_type.strip().lower() or "text/html",
                charset=charset,
                truncated=truncated,
            )
    except asyncio.TimeoutError:
        raise BrowserAcquisitionError("browser_timeout") from None


async def fetch_page_html(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    proxy: str | None = None,
) -> BrowserPageOutcome:
    """Load the page and return its raw HTML (search parsers, SPEC 5.4)."""

    try:
        async with _validated_page(url, timeout_seconds=timeout_seconds, proxy=proxy) as (
            page,
            _response,
        ):
            content = await page.content()
            if not content.strip():
                raise BrowserAcquisitionError("empty_content")
            truncated = len(content) > _MAX_CODE_POINTS
            return BrowserPageOutcome(
                final_url=str(page.url),
                title=(await page.title()).strip() or None,
                content=content[:_MAX_CODE_POINTS],
                media_type="text/html",
                charset=None,
                truncated=truncated,
            )
    except asyncio.TimeoutError:
        raise BrowserAcquisitionError("browser_timeout") from None
