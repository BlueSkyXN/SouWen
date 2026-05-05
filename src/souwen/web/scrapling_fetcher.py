"""Scrapling 内容抓取客户端。

Scrapling 是本地运行的抓取框架，提供普通 HTTP、动态浏览器和 stealth 浏览器三类
fetcher。这里把它封装成 SouWen 的 fetch provider，使用户可以通过
``souwen fetch --provider scrapling`` 或 ``fetch_content(..., provider="scrapling")``
使用，而不会影响现有 ``httpx`` / ``curl_cffi`` 后端。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Literal
from urllib.parse import urlparse

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.scrapling_fetcher")


_ROBOTS_USER_AGENT = "SouWenBot/1.0"
_Mode = Literal["fetcher", "dynamic", "stealthy"]
_ContentFormat = Literal["text", "html"]


_FETCHER_PARAM_KEYS = frozenset(
    {
        "stealthy_headers",
        "follow_redirects",
        "impersonate",
        "http3",
        "max_redirects",
        "verify",
        "retries",
        "retry_delay",
    }
)
_BROWSER_PARAM_KEYS = frozenset(
    {
        "headless",
        "disable_resources",
        "useragent",
        "network_idle",
        "load_dom",
        "wait",
        "wait_selector",
        "wait_selector_state",
        "google_search",
        "real_chrome",
        "locale",
        "timezone_id",
        "cdp_url",
        "user_data_dir",
        "block_ads",
        "retries",
        "retry_delay",
        "capture_xhr",
        "executable_path",
    }
)
_STEALTH_PARAM_KEYS = _BROWSER_PARAM_KEYS | frozenset(
    {
        "solve_cloudflare",
        "block_webrtc",
        "hide_canvas",
        "allow_webgl",
    }
)


def _normalize_mode(value: object) -> _Mode:
    mode = str(value or "fetcher").strip().lower().replace("-", "_")
    if mode in {"http", "static", "request", "requests"}:
        return "fetcher"
    if mode in {"browser", "playwright"}:
        return "dynamic"
    if mode in {"stealth", "stealthy"}:
        return "stealthy"
    if mode in {"fetcher", "dynamic", "stealthy"}:
        return mode  # type: ignore[return-value]
    raise ValueError("sources.scrapling.params.mode 只能是 fetcher / dynamic / stealthy")


def _normalize_content_format(value: object) -> _ContentFormat:
    fmt = str(value or "text").strip().lower()
    if fmt in {"text", "txt"}:
        return "text"
    if fmt in {"html", "raw_html"}:
        return "html"
    raise ValueError("sources.scrapling.params.content_format 只能是 text / html")


def _filter_params(
    params: dict[str, str | int | float | bool], allowed: frozenset[str]
) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k in allowed}


def _safe_follow_redirects(value: object) -> bool | str:
    if value is False:
        return False
    if isinstance(value, str) and value.strip().lower() in {"false", "0", "no", "off"}:
        return False
    return "safe"


class ScraplingFetcherClient:
    """Scrapling fetch provider。

    默认 ``mode=fetcher`` 使用 Scrapling 的 ``AsyncFetcher``，适合不需要 JS 的页面；
    ``mode=dynamic`` / ``mode=stealthy`` 会启动浏览器，适合 JS 或反爬页面。
    """

    PROVIDER_NAME = "scrapling"
    DEFAULT_MAX_CONCURRENCY = 2

    def __init__(self, mode: str | None = None) -> None:
        self._mode_override = mode
        self._async_fetcher: Any = None
        self._dynamic_fetcher: Any = None
        self._stealthy_fetcher: Any = None
        self._robots_cache: dict[str, Any | None] = {}

    async def __aenter__(self) -> "ScraplingFetcherClient":
        try:
            from scrapling.fetchers import AsyncFetcher, DynamicFetcher, StealthyFetcher
        except ImportError:
            raise ConfigError(
                "scrapling[fetchers]",
                "Scrapling",
                'pip install -e ".[scrapling]" 或 pip install "souwen[scrapling]"，然后执行 scrapling install',
            ) from None

        self._async_fetcher = AsyncFetcher
        self._dynamic_fetcher = DynamicFetcher
        self._stealthy_fetcher = StealthyFetcher
        return self

    async def __aexit__(self, *args: Any) -> None:
        self._async_fetcher = None
        self._dynamic_fetcher = None
        self._stealthy_fetcher = None

    def _request_options(self, timeout: float) -> tuple[_Mode, _ContentFormat, dict[str, Any]]:
        cfg = get_config()
        params = dict(cfg.resolve_params(self.PROVIDER_NAME))
        mode = _normalize_mode(self._mode_override or params.pop("mode", "fetcher"))
        content_format = _normalize_content_format(params.pop("content_format", "text"))

        if mode == "fetcher":
            options = _filter_params(params, _FETCHER_PARAM_KEYS)
            options.setdefault("timeout", timeout)
            options["follow_redirects"] = _safe_follow_redirects(
                options.get("follow_redirects", "safe")
            )
            headers = cfg.resolve_headers(self.PROVIDER_NAME)
            if headers and "headers" not in options:
                options["headers"] = headers
        elif mode == "dynamic":
            options = _filter_params(params, _BROWSER_PARAM_KEYS)
            options.setdefault("timeout", int(timeout * 1000))
            options["page_setup"] = self._browser_page_setup()
            headers = cfg.resolve_headers(self.PROVIDER_NAME)
            if headers and "extra_headers" not in options:
                options["extra_headers"] = headers
        else:
            options = _filter_params(params, _STEALTH_PARAM_KEYS)
            options.setdefault("timeout", int(timeout * 1000))
            options["page_setup"] = self._browser_page_setup()
            headers = cfg.resolve_headers(self.PROVIDER_NAME)
            if headers and "extra_headers" not in options:
                options["extra_headers"] = headers

        proxy = cfg.resolve_proxy(self.PROVIDER_NAME)
        if proxy and "proxy" not in options:
            options["proxy"] = proxy
        return mode, content_format, options

    @staticmethod
    async def _call_route_method(route: Any, method_name: str) -> None:
        method = getattr(route, method_name, None)
        if method is None:
            return
        result = method()
        if inspect.isawaitable(result):
            await result

    @classmethod
    def _browser_page_setup(cls):
        """给 Scrapling 浏览器模式安装请求层 SSRF 防护。"""

        async def _setup(page: Any) -> None:
            from souwen.web.fetch import validate_fetch_url

            async def _guard_route(route: Any) -> None:
                request = getattr(route, "request", None)
                target_url = str(getattr(request, "url", "") or "")
                ok, reason = validate_fetch_url(target_url)
                if ok:
                    # fallback 可保留 Scrapling/Playwright 后续 route 规则；旧版本退回 continue_。
                    proceed = "fallback" if hasattr(route, "fallback") else "continue_"
                    await cls._call_route_method(route, proceed)
                    return

                logger.warning(
                    "Scrapling browser SSRF blocked: url=%s reason=%s",
                    target_url,
                    reason,
                )
                await cls._call_route_method(route, "abort")

            result = page.route("**/*", _guard_route)
            if inspect.isawaitable(result):
                await result

        return _setup

    async def _check_robots(self, url: str, timeout: float) -> tuple[bool, str]:
        """按 scheme+host 缓存 robots.txt 检查结果。

        robots 检查采用 fail-open：依赖缺失、robots.txt 获取失败或解析异常时不阻断抓取。
        """
        try:
            from protego import Protego
        except ImportError:
            logger.debug("protego 未安装，跳过 Scrapling robots.txt 检查")
            return True, ""

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True, ""
        origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin not in self._robots_cache:
            robots_url = f"{origin}/robots.txt"
            try:
                from souwen.web.fetch import validate_fetch_url

                ok, reason = validate_fetch_url(robots_url)
                if not ok:
                    logger.debug("robots.txt URL 未通过 SSRF 校验 %s: %s", robots_url, reason)
                    self._robots_cache[origin] = None
                elif self._async_fetcher is None:
                    self._robots_cache[origin] = None
                else:
                    options: dict[str, Any] = {
                        "timeout": min(float(timeout), 10.0),
                        "follow_redirects": "safe",
                        "retries": 1,
                        "headers": {"User-Agent": _ROBOTS_USER_AGENT},
                    }
                    proxy = get_config().resolve_proxy(self.PROVIDER_NAME)
                    if proxy:
                        options["proxy"] = proxy
                    page = await self._async_fetcher.get(robots_url, **options)
                    status = int(getattr(page, "status", 0) or 0)
                    body = getattr(page, "body", b"")
                    if isinstance(body, bytes):
                        encoding = str(getattr(page, "encoding", "") or "utf-8")
                        text = body.decode(encoding, errors="replace")
                    else:
                        text = str(body or getattr(page, "html_content", "") or "")
                    self._robots_cache[origin] = (
                        Protego.parse(text) if 200 <= status < 300 and text else None
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Scrapling robots.txt 检查失败 %s: %s", robots_url, exc)
                self._robots_cache[origin] = None

        parser = self._robots_cache.get(origin)
        if parser is None:
            return True, ""
        try:
            allowed = parser.can_fetch(url, _ROBOTS_USER_AGENT)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Scrapling robots.txt 解析异常 %s: %s", url, exc)
            return True, ""
        if not allowed:
            return False, f"robots.txt 拒绝抓取（UA={_ROBOTS_USER_AGENT}）"
        return True, ""

    async def _fetch_page(self, url: str, timeout: float) -> tuple[Any, _Mode, _ContentFormat]:
        mode, content_format, options = self._request_options(timeout)
        if mode == "fetcher":
            if self._async_fetcher is None:
                raise RuntimeError("Scrapling AsyncFetcher 未初始化")
            page = await self._async_fetcher.get(url, **options)
        elif mode == "dynamic":
            if self._dynamic_fetcher is None:
                raise RuntimeError("Scrapling DynamicFetcher 未初始化")
            page = await self._dynamic_fetcher.async_fetch(url, **options)
        else:
            if self._stealthy_fetcher is None:
                raise RuntimeError("Scrapling StealthyFetcher 未初始化")
            page = await self._stealthy_fetcher.async_fetch(url, **options)
        return page, mode, content_format

    @staticmethod
    def _selected_content(page: Any, selector: str | None, content_format: _ContentFormat) -> str:
        if selector:
            selected = page.css(selector)
            if content_format == "html":
                return "\n".join(str(item) for item in selected.getall())
            chunks: list[str] = []
            for item in selected:
                text = item.get_all_text(separator="\n", strip=True)
                if text:
                    chunks.append(str(text))
            return "\n".join(chunks)

        if content_format == "html":
            return str(getattr(page, "html_content", "") or "")
        text = page.get_all_text(separator="\n", strip=True)
        return str(text or "")

    @staticmethod
    def _title_from_page(page: Any) -> str:
        try:
            title = page.css("title::text").get("")
        except Exception:
            return ""
        return str(title or "")

    @staticmethod
    def _truncate(
        content: str, start_index: int, max_length: int | None
    ) -> tuple[str, bool, int | None]:
        start = max(0, int(start_index or 0))
        sliced = content[start:]
        if max_length is None:
            return sliced, False, None
        limit = max(0, int(max_length))
        truncated = len(sliced) > limit
        if not truncated:
            return sliced, False, None
        return sliced[:limit], True, start + limit

    async def fetch(
        self,
        url: str,
        timeout: float = 30.0,
        *,
        selector: str | None = None,
        start_index: int = 0,
        max_length: int | None = None,
        respect_robots_txt: bool = False,
    ) -> FetchResult:
        """抓取单个 URL 并归一化为 SouWen ``FetchResult``。"""
        try:
            if respect_robots_txt:
                allowed, reason = await self._check_robots(url, timeout)
                if not allowed:
                    logger.info("Scrapling robots.txt 拒绝: %s (%s)", url, reason)
                    return FetchResult(
                        url=url,
                        final_url=url,
                        source=self.PROVIDER_NAME,
                        error=reason,
                        raw={"provider": self.PROVIDER_NAME, "blocked_by_robots": True},
                    )

            page, mode, content_format = await self._fetch_page(url, timeout)
            content = self._selected_content(page, selector, content_format)
            content, truncated, next_start = self._truncate(content, start_index, max_length)
            status = getattr(page, "status", None)
            final_url = str(getattr(page, "url", "") or url)
            title = self._title_from_page(page)
            return FetchResult(
                url=url,
                final_url=final_url,
                title=title,
                content=content,
                content_format=content_format,
                content_truncated=truncated,
                next_start_index=next_start,
                source=self.PROVIDER_NAME,
                snippet=content[:500],
                raw={
                    "provider": self.PROVIDER_NAME,
                    "mode": mode,
                    "status": status,
                    "reason": getattr(page, "reason", ""),
                    "selector": selector,
                    "respect_robots_txt": respect_robots_txt,
                },
            )
        except asyncio.TimeoutError:
            logger.warning("Scrapling fetch timeout: url=%s timeout=%.1fs", url, timeout)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=f"抓取超时 ({timeout}s)",
            )
        except Exception as exc:
            logger.warning("Scrapling fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": self.PROVIDER_NAME},
            )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        timeout: float = 30.0,
        *,
        selector: str | None = None,
        start_index: int = 0,
        max_length: int | None = None,
        respect_robots_txt: bool = False,
    ) -> FetchResponse:
        """批量抓取 URL。"""
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(u: str) -> FetchResult:
            async with sem:
                return await self.fetch(
                    u,
                    timeout=timeout,
                    selector=selector,
                    start_index=start_index,
                    max_length=max_length,
                    respect_robots_txt=respect_robots_txt,
                )

        results = list(await asyncio.gather(*[_fetch_one(url) for url in urls]))
        ok = sum(1 for item in results if item.error is None)
        return FetchResponse(
            urls=urls,
            results=results,
            total=len(results),
            total_ok=ok,
            total_failed=len(results) - ok,
            provider=self.PROVIDER_NAME,
        )
