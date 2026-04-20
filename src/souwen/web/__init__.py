"""常规网页搜索模块

提供 15 个搜索引擎客户端，分为爬虫和 API 两类：

爬虫类（无需 Key，零配置即用）：
- DuckDuckGoClient: DuckDuckGo HTML 搜索
- YahooClient: Yahoo 搜索（Bing 驱动）
- BraveClient: Brave 独立索引搜索
- GoogleClient: Google 搜索（高风险，建议配代理）
- BingClient: Bing 搜索
- StartpageClient: Startpage 隐私搜索（Google 结果）
- BaiduClient: 百度搜索（中文首选）
- MojeekClient: Mojeek 独立索引搜索（英国）
- YandexClient: Yandex 搜索（俄罗斯）

API 类（需 Key / 自建实例）：
- SearXNGClient: SearXNG 元搜索（250+ 引擎）
- TavilyClient: Tavily AI 搜索（为 Agent 设计）
- ExaClient: Exa 语义搜索（神经索引）
- SerperClient: Serper Google SERP API
- BraveApiClient: Brave 官方 API
- MetasoClient: 秘塔搜索（文档/网页/学术三种范围）

聚合搜索：
- web_search(): 并发多引擎聚合 + URL 去重
"""

from souwen.web.duckduckgo import DuckDuckGoClient
from souwen.web.yahoo import YahooClient
from souwen.web.brave import BraveClient
from souwen.web.google import GoogleClient
from souwen.web.bing import BingClient
from souwen.web.startpage import StartpageClient
from souwen.web.baidu import BaiduClient
from souwen.web.mojeek import MojeekClient
from souwen.web.yandex import YandexClient
from souwen.web.searxng import SearXNGClient
from souwen.web.tavily import TavilyClient
from souwen.web.exa import ExaClient
from souwen.web.serper import SerperClient
from souwen.web.brave_api import BraveApiClient
from souwen.web.serpapi import SerpApiClient
from souwen.web.firecrawl import FirecrawlClient
from souwen.web.perplexity import PerplexityClient
from souwen.web.linkup import LinkupClient
from souwen.web.scrapingdog import ScrapingDogClient
from souwen.web.whoogle import WhoogleClient
from souwen.web.websurfx import WebsurfxClient
from souwen.web.github import GitHubClient
from souwen.web.stackoverflow import StackOverflowClient
from souwen.web.reddit import RedditClient
from souwen.web.bilibili import BilibiliClient
from souwen.web.wikipedia import WikipediaClient
from souwen.web.youtube import YouTubeClient
from souwen.web.zhihu import ZhihuClient
from souwen.web.weibo import WeiboClient
from souwen.web.metaso import MetasoClient
from souwen.web.jina_reader import JinaReaderClient
from souwen.web.builtin import BuiltinFetcherClient
from souwen.web.search import web_search
from souwen.web.fetch import fetch_content

__all__ = [
    # 爬虫类（无需 Key）
    "DuckDuckGoClient",
    "YahooClient",
    "BraveClient",
    "GoogleClient",
    "BingClient",
    "StartpageClient",
    "BaiduClient",
    "MojeekClient",
    "YandexClient",
    # API 类（需 Key）
    "SearXNGClient",
    "TavilyClient",
    "ExaClient",
    "SerperClient",
    "BraveApiClient",
    "SerpApiClient",
    "FirecrawlClient",
    "PerplexityClient",
    "LinkupClient",
    "ScrapingDogClient",
    # 自建实例类
    "WhoogleClient",
    "WebsurfxClient",
    # 社交/平台类
    "GitHubClient",
    "StackOverflowClient",
    "RedditClient",
    "BilibiliClient",
    "WikipediaClient",
    "YouTubeClient",
    "ZhihuClient",
    "WeiboClient",
    # API 类（需 Key）- 中文搜索
    "MetasoClient",
    # 内容抓取类 (fetch)
    "BuiltinFetcherClient",
    "JinaReaderClient",
    # 聚合搜索/抓取
    "web_search",
    "fetch_content",
]
