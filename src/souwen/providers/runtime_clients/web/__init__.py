"""常规网页搜索模块

提供 15 个搜索引擎客户端，分为爬虫和 API 两类：

爬虫类（无需 Key，零配置即用）：
- DuckDuckGoClient: DuckDuckGo HTML 搜索
- YahooClient: Yahoo 搜索（Bing 驱动）
- BraveClient: Brave 独立索引搜索
- GoogleClient: Google 搜索（高风险，建议配代理）
- BingClient: Bing 搜索
- BingCnClient: 必应中文搜索（cn.bing.com，中文优化）
- StartpageClient: Startpage 隐私搜索（Google 结果）
- BaiduClient: 百度搜索（中文首选）
- MojeekClient: Mojeek 独立索引搜索（英国）
- YandexClient: Yandex 搜索（俄罗斯）

办公/企业平台（官方 API）：

API 类（需 Key / 自建实例）：
- SearXNGClient: SearXNG 元搜索（250+ 引擎）

内容抓取（fetch 提供者）：

辅助函数：

"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "DuckDuckGoClient": ("souwen.providers.runtime_clients.web.duckduckgo", "DuckDuckGoClient"),
    "DuckDuckGoNewsClient": (
        "souwen.providers.runtime_clients.web.ddg_news",
        "DuckDuckGoNewsClient",
    ),
    "DuckDuckGoImagesClient": (
        "souwen.providers.runtime_clients.web.ddg_images",
        "DuckDuckGoImagesClient",
    ),
    "ImageSearchResult": ("souwen.providers.runtime_clients.web.ddg_images", "ImageSearchResult"),
    "ImageSearchResponse": (
        "souwen.providers.runtime_clients.web.ddg_images",
        "ImageSearchResponse",
    ),
    "DuckDuckGoVideosClient": (
        "souwen.providers.runtime_clients.web.ddg_videos",
        "DuckDuckGoVideosClient",
    ),
    "VideoSearchResult": ("souwen.providers.runtime_clients.web.ddg_videos", "VideoSearchResult"),
    "VideoSearchResponse": (
        "souwen.providers.runtime_clients.web.ddg_videos",
        "VideoSearchResponse",
    ),
    "YahooClient": ("souwen.providers.runtime_clients.web.yahoo", "YahooClient"),
    "BraveClient": ("souwen.providers.runtime_clients.web.brave", "BraveClient"),
    "GoogleClient": ("souwen.providers.runtime_clients.web.google", "GoogleClient"),
    "BingClient": ("souwen.providers.runtime_clients.web.bing", "BingClient"),
    "BingCnClient": ("souwen.providers.runtime_clients.web.bing_cn", "BingCnClient"),
    "StartpageClient": ("souwen.providers.runtime_clients.web.startpage", "StartpageClient"),
    "BaiduClient": ("souwen.providers.runtime_clients.web.baidu", "BaiduClient"),
    "MojeekClient": ("souwen.providers.runtime_clients.web.mojeek", "MojeekClient"),
    "YandexClient": ("souwen.providers.runtime_clients.web.yandex", "YandexClient"),
    "SearXNGClient": ("souwen.providers.runtime_clients.web.searxng", "SearXNGClient"),
    "GitHubClient": ("souwen.providers.runtime_clients.web.github", "GitHubClient"),
    "StackOverflowClient": (
        "souwen.providers.runtime_clients.web.stackoverflow",
        "StackOverflowClient",
    ),
    "BilibiliClient": ("souwen.providers.runtime_clients.web.bilibili", "BilibiliClient"),
    "WikipediaClient": ("souwen.providers.runtime_clients.web.wikipedia", "WikipediaClient"),
    "YouTubeClient": ("souwen.providers.runtime_clients.web.youtube", "YouTubeClient"),
    "VideoDetail": ("souwen.providers.runtime_clients.web.youtube", "VideoDetail"),
    "CSDNClient": ("souwen.providers.runtime_clients.web.csdn", "CSDNClient"),
    "JuejinClient": ("souwen.providers.runtime_clients.web.juejin", "JuejinClient"),
    "NodeSeekClient": ("souwen.providers.runtime_clients.web.nodeseek", "NodeSeekClient"),
    "HostLocClient": ("souwen.providers.runtime_clients.web.hostloc", "HostLocClient"),
    "V2EXClient": ("souwen.providers.runtime_clients.web.v2ex", "V2EXClient"),
    "CoolapkClient": ("souwen.providers.runtime_clients.web.coolapk", "CoolapkClient"),
    "XiaohongshuClient": ("souwen.providers.runtime_clients.web.xiaohongshu", "XiaohongshuClient"),
    "JinaReaderClient": ("souwen.providers.runtime_clients.web.jina_reader", "JinaReaderClient"),
    "BuiltinFetcherClient": (
        "souwen.providers.runtime_clients.web.builtin",
        "BuiltinFetcherClient",
    ),
    "WaybackClient": ("souwen.providers.runtime_clients.web.wayback", "WaybackClient"),
}


def __getattr__(name: str) -> Any:
    """按需加载兼容的 ``souwen.providers.runtime_clients.web`` convenience exports。"""

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
    # 爬虫类（无需 Key）
    "DuckDuckGoClient",
    "DuckDuckGoNewsClient",
    "DuckDuckGoImagesClient",
    "DuckDuckGoVideosClient",
    "ImageSearchResult",
    "ImageSearchResponse",
    "VideoSearchResult",
    "VideoSearchResponse",
    "YahooClient",
    "BraveClient",
    "GoogleClient",
    "BingClient",
    "BingCnClient",
    "StartpageClient",
    "BaiduClient",
    "MojeekClient",
    "YandexClient",
    # API 类（需 Key）
    "SearXNGClient",
    # 自建实例类
    # 社交/平台类
    "GitHubClient",
    "StackOverflowClient",
    "BilibiliClient",
    "WikipediaClient",
    "YouTubeClient",
    "VideoDetail",
    # 中文技术社区
    "CSDNClient",
    "JuejinClient",
    "NodeSeekClient",
    "HostLocClient",
    "V2EXClient",
    "CoolapkClient",
    "XiaohongshuClient",
    # 国际社交媒体（官方 API）
    # 办公/企业平台（官方 API）
    # API 类（需 Key）- 中文搜索
    # 内容抓取类 (fetch)
    "BuiltinFetcherClient",
    "JinaReaderClient",
    "WaybackClient",
    # DeepWiki
]
