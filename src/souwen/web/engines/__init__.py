"""web/engines/ — 网页搜索引擎（爬虫类，v1）

13 个爬虫 SERP：duckduckgo / yahoo / brave / google / bing / bing_cn / startpage /
baidu / mojeek / yandex + DDG 变种（news / images / videos）。
"""

from souwen.web.baidu import BaiduClient
from souwen.web.bing import BingClient
from souwen.web.bing_cn import BingCnClient
from souwen.web.brave import BraveClient
from souwen.web.ddg_images import DuckDuckGoImagesClient
from souwen.web.ddg_news import DuckDuckGoNewsClient
from souwen.web.ddg_videos import DuckDuckGoVideosClient
from souwen.web.duckduckgo import DuckDuckGoClient
from souwen.web.google import GoogleClient
from souwen.web.mojeek import MojeekClient
from souwen.web.startpage import StartpageClient
from souwen.web.yahoo import YahooClient
from souwen.web.yandex import YandexClient

__all__ = [
    "DuckDuckGoClient",
    "DuckDuckGoNewsClient",
    "DuckDuckGoImagesClient",
    "DuckDuckGoVideosClient",
    "YahooClient",
    "BraveClient",
    "GoogleClient",
    "BingClient",
    "BingCnClient",
    "StartpageClient",
    "BaiduClient",
    "MojeekClient",
    "YandexClient",
]
