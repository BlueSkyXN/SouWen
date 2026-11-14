"""历史导入路径转发：各源 client 已并入 information_sources/fetch_sources 的 source.py。"""

from __future__ import annotations

from souwen.providers.information_sources.github.source import GitHubClient  # noqa: F401
from souwen.providers.information_sources.stackoverflow.source import StackOverflowClient  # noqa: F401
from souwen.providers.information_sources.wikipedia.source import WikipediaClient  # noqa: F401
from souwen.providers.information_sources.youtube.source import YouTubeClient  # noqa: F401
from souwen.providers.information_sources.baidu.source import BaiduClient  # noqa: F401
from souwen.providers.information_sources.brave.source import BraveClient  # noqa: F401
from souwen.providers.information_sources.duckduckgo_news.source import DuckDuckGoNewsClient  # noqa: F401
from souwen.providers.information_sources.juejin.source import JuejinClient  # noqa: F401
from souwen.providers.information_sources.coolapk.source import CoolapkClient  # noqa: F401
from souwen.providers.information_sources.searxng.source import SearXNGClient  # noqa: F401
from souwen.providers.fetch_sources.jina_reader.source import JinaReaderClient  # noqa: F401
from souwen.providers.fetch_sources.wayback.source import WaybackClient  # noqa: F401

__all__ = [
    "GitHubClient",
    "StackOverflowClient",
    "WikipediaClient",
    "YouTubeClient",
    "BaiduClient",
    "BraveClient",
    "DuckDuckGoNewsClient",
    "JuejinClient",
    "CoolapkClient",
    "SearXNGClient",
    "JinaReaderClient",
    "WaybackClient",
]
