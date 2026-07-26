"""Lazy Playwright browser pooling for scraper fallbacks.

The pool keeps one browser process per event loop and launch key, while each
call gets an isolated browser context/page. Playwright is imported only when a
browser page is actually requested, so regular imports and deterministic tests
do not require the optional browser runtime.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, SourceUnavailableError
from souwen.core.fingerprint import get_random_fingerprint


_DEFAULT_MAX_PAGES = 2


@dataclass(frozen=True)
class BrowserPoolKey:
    """Launch options that require a separate browser process."""

    browser_name: str = "chromium"
    headless: bool = True
    proxy: str | None = None
    host_resolver_rules: tuple[tuple[str, str], ...] = ()


def _host_resolver_argument(rules: tuple[tuple[str, str], ...]) -> str | None:
    """Build a Chromium host pinning argument from validated hostname/IP pairs."""
    if not rules:
        return None
    mappings: list[str] = []
    for hostname, address in rules:
        normalized_host = hostname.strip().lower()
        if (
            not normalized_host
            or any(character in normalized_host for character in " ,/=\t\r\n")
            or normalized_host.startswith("[")
        ):
            raise ValueError("invalid browser host resolver hostname")
        parsed_address = ipaddress.ip_address(address)
        if not parsed_address.is_global:
            raise ValueError("browser host resolver address must be public")
        rendered_address = (
            f"[{parsed_address.compressed}]"
            if isinstance(parsed_address, ipaddress.IPv6Address)
            else parsed_address.compressed
        )
        mappings.append(f"MAP {normalized_host} {rendered_address}")
    mappings.append("MAP * ~NOTFOUND")
    return ",".join(mappings)


def _max_pages_from_env() -> int:
    raw = os.environ.get("SOUWEN_BROWSER_POOL_MAX_PAGES")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return _DEFAULT_MAX_PAGES


class PlaywrightBrowserPool:
    """One lazy Playwright browser with bounded concurrent pages."""

    def __init__(self, key: BrowserPoolKey | None = None, *, max_pages: int | None = None):
        self.key = key or BrowserPoolKey()
        self.max_pages = max_pages if max_pages and max_pages > 0 else _max_pages_from_env()
        self._playwright: Any = None
        self._browser: Any = None
        self._startup_lock: asyncio.Lock | None = None
        self._page_semaphore: asyncio.Semaphore | None = None

    @property
    def started(self) -> bool:
        """Return whether a connected browser is currently held."""

        if self._browser is None:
            return False
        is_connected = getattr(self._browser, "is_connected", None)
        if callable(is_connected):
            return bool(is_connected())
        return True

    def _lock(self) -> asyncio.Lock:
        if self._startup_lock is None:
            self._startup_lock = asyncio.Lock()
        return self._startup_lock

    def _semaphore(self) -> asyncio.Semaphore:
        if self._page_semaphore is None:
            self._page_semaphore = asyncio.Semaphore(self.max_pages)
        return self._page_semaphore

    async def _ensure_browser(self) -> Any:
        if self.started:
            return self._browser

        async with self._lock():
            if self.started:
                return self._browser

            try:
                from playwright.async_api import async_playwright
            except ImportError:
                raise ConfigError(
                    "playwright",
                    "Playwright browser runtime",
                    'pip install "playwright>=1.40" && python -m playwright install chromium',
                ) from None

            playwright = await async_playwright().start()
            try:
                browser_type = getattr(playwright, self.key.browser_name)
            except AttributeError as exc:
                await playwright.stop()
                raise SourceUnavailableError(
                    f"未知 Playwright browser: {self.key.browser_name}"
                ) from exc

            launch_options: dict[str, Any] = {"headless": self.key.headless}
            if self.key.proxy:
                launch_options["proxy"] = {"server": self.key.proxy}
                launch_options["args"] = ["--proxy-bypass-list=<-loopback>"]
            resolver_argument = _host_resolver_argument(self.key.host_resolver_rules)
            if resolver_argument is not None:
                launch_options.setdefault("args", []).append(
                    f"--host-resolver-rules={resolver_argument}"
                )

            try:
                self._browser = await browser_type.launch(**launch_options)
            except Exception as exc:
                await playwright.stop()
                raise SourceUnavailableError(f"Playwright browser 启动失败: {exc}") from exc

            self._playwright = playwright
            return self._browser

    async def new_context(
        self,
        *,
        user_agent: str | None = None,
        extra_http_headers: dict[str, str] | None = None,
        viewport: dict[str, int] | None = None,
        locale: str | None = None,
        timezone_id: str | None = None,
        accept_downloads: bool | None = None,
        service_workers: str | None = None,
        proxy: str | None = None,
    ) -> Any:
        """Create an isolated browser context from the pooled browser."""

        browser = await self._ensure_browser()
        options: dict[str, Any] = {}
        fingerprint = get_random_fingerprint()
        options["user_agent"] = user_agent or fingerprint.user_agent
        if extra_http_headers:
            options["extra_http_headers"] = extra_http_headers
        if viewport:
            options["viewport"] = viewport
        if locale:
            options["locale"] = locale
        if timezone_id:
            options["timezone_id"] = timezone_id
        if accept_downloads is not None:
            options["accept_downloads"] = accept_downloads
        if service_workers is not None:
            options["service_workers"] = service_workers
        if proxy is not None:
            options["proxy"] = {"server": proxy}
        return await browser.new_context(**options)

    @asynccontextmanager
    async def page(
        self,
        *,
        user_agent: str | None = None,
        extra_http_headers: dict[str, str] | None = None,
        viewport: dict[str, int] | None = None,
        locale: str | None = None,
        timezone_id: str | None = None,
        accept_downloads: bool | None = None,
        service_workers: str | None = None,
        proxy: str | None = None,
    ) -> AsyncIterator[Any]:
        """Yield a page and always close its context afterward."""

        async with self._semaphore():
            context = await self.new_context(
                user_agent=user_agent,
                extra_http_headers=extra_http_headers,
                viewport=viewport,
                locale=locale,
                timezone_id=timezone_id,
                accept_downloads=accept_downloads,
                service_workers=service_workers,
                proxy=proxy,
            )
            page = await context.new_page()
            try:
                yield page
            finally:
                close = getattr(context, "close", None)
                if close is not None:
                    await close()

    async def close(self) -> None:
        """Close the browser process and Playwright driver."""

        browser = self._browser
        playwright = self._playwright
        self._browser = None
        self._playwright = None

        if browser is not None:
            close = getattr(browser, "close", None)
            if close is not None:
                await close()
        if playwright is not None:
            await playwright.stop()


_pools: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[BrowserPoolKey, PlaywrightBrowserPool]]" = (  # noqa: E501
    weakref.WeakKeyDictionary()
)


def get_browser_pool(
    *,
    source_name: str | None = None,
    browser_name: str = "chromium",
    headless: bool = True,
    max_pages: int | None = None,
) -> PlaywrightBrowserPool:
    """Return a per-loop browser pool for the resolved launch options."""

    cfg = get_config()
    proxy = cfg.resolve_proxy(source_name) if source_name else cfg.get_proxy()
    key = BrowserPoolKey(browser_name=browser_name, headless=headless, proxy=proxy)

    loop = asyncio.get_running_loop()
    pools = _pools.get(loop)
    if pools is None:
        pools = {}
        _pools[loop] = pools
    pool = pools.get(key)
    if pool is None:
        pool = PlaywrightBrowserPool(key, max_pages=max_pages)
        pools[key] = pool
    return pool


async def close_browser_pools() -> None:
    """Close and clear all browser pools for the current event loop."""

    loop = asyncio.get_running_loop()
    pools = _pools.get(loop)
    if not pools:
        return
    for pool in list(pools.values()):
        await pool.close()
    pools.clear()


__all__ = [
    "BrowserPoolKey",
    "PlaywrightBrowserPool",
    "close_browser_pools",
    "get_browser_pool",
]
