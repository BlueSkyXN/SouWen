"""常规网页搜索与抓取客户端（P3 终判后的存活集合）。

爬虫类（无需 Key，零配置即用）：
- YahooClient: Yahoo 搜索
- BraveClient: Brave 独立索引搜索
- BaiduClient: 百度搜索（中文首选）

API / 自建类（需 Key / 实例）：
- SearXNGClient: SearXNG 元搜索（由配置的实例 URL 启用）

平台类：
- GitHubClient / StackOverflowClient / WikipediaClient / YouTubeClient
- JuejinClient / CoolapkClient（中文技术社区）

内容抓取（fetch 提供者）：
- BuiltinFetcherClient / JinaReaderClient / WaybackClient
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "YahooClient": ("souwen.providers.runtime_clients.web.yahoo", "YahooClient"),
    "BraveClient": ("souwen.providers.runtime_clients.web.brave", "BraveClient"),
    "BaiduClient": ("souwen.providers.runtime_clients.web.baidu", "BaiduClient"),
    "SearXNGClient": ("souwen.providers.runtime_clients.web.searxng", "SearXNGClient"),
    "GitHubClient": ("souwen.providers.runtime_clients.web.github", "GitHubClient"),
    "StackOverflowClient": (
        "souwen.providers.runtime_clients.web.stackoverflow",
        "StackOverflowClient",
    ),
    "WikipediaClient": ("souwen.providers.runtime_clients.web.wikipedia", "WikipediaClient"),
    "YouTubeClient": ("souwen.providers.runtime_clients.web.youtube", "YouTubeClient"),
    "JuejinClient": ("souwen.providers.runtime_clients.web.juejin", "JuejinClient"),
    "CoolapkClient": ("souwen.providers.runtime_clients.web.coolapk", "CoolapkClient"),
    "BuiltinFetcherClient": (
        "souwen.providers.runtime_clients.web.builtin",
        "BuiltinFetcherClient",
    ),
    "JinaReaderClient": ("souwen.providers.runtime_clients.web.jina_reader", "JinaReaderClient"),
    "WaybackClient": ("souwen.providers.runtime_clients.web.wayback", "WaybackClient"),
    "ImageSearchResult": ("souwen.providers.runtime_clients.web.models", "ImageSearchResult"),
    "ImageSearchResponse": ("souwen.providers.runtime_clients.web.models", "ImageSearchResponse"),
    "VideoSearchResult": ("souwen.providers.runtime_clients.web.models", "VideoSearchResult"),
    "VideoSearchResponse": ("souwen.providers.runtime_clients.web.models", "VideoSearchResponse"),
    "VideoDetail": ("souwen.providers.runtime_clients.web.models", "VideoDetail"),
}


def __getattr__(name: str) -> Any:
    """按需加载 ``souwen.providers.runtime_clients.web`` convenience exports。"""

    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = [
    "YahooClient",
    "BraveClient",
    "BaiduClient",
    "SearXNGClient",
    "GitHubClient",
    "StackOverflowClient",
    "WikipediaClient",
    "YouTubeClient",
    "JuejinClient",
    "CoolapkClient",
    "BuiltinFetcherClient",
    "JinaReaderClient",
    "WaybackClient",
    "ImageSearchResult",
    "ImageSearchResponse",
    "VideoSearchResult",
    "VideoSearchResponse",
    "VideoDetail",
]
