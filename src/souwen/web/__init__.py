"""常规网页搜索模块

提供 10 个搜索引擎客户端，分为爬虫和 API 两类：

爬虫类（无需 Key，零配置即用）：
- DuckDuckGoClient: DuckDuckGo HTML 搜索
- YahooClient: Yahoo 搜索（Bing 驱动）
- BraveClient: Brave 独立索引搜索
- GoogleClient: Google 搜索（高风险，建议配代理）
- BingClient: Bing 搜索

API 类（需 Key / 自建实例）：
- SearXNGClient: SearXNG 元搜索（250+ 引擎）
- TavilyClient: Tavily AI 搜索（为 Agent 设计）
- ExaClient: Exa 语义搜索（神经索引）
- SerperClient: Serper Google SERP API
- BraveApiClient: Brave 官方 API

聚合搜索：
- web_search(): 并发多引擎聚合 + URL 去重
"""

from souwen.web.duckduckgo import DuckDuckGoClient
from souwen.web.yahoo import YahooClient
from souwen.web.brave import BraveClient
from souwen.web.google import GoogleClient
from souwen.web.bing import BingClient
from souwen.web.searxng import SearXNGClient
from souwen.web.tavily import TavilyClient
from souwen.web.exa import ExaClient
from souwen.web.serper import SerperClient
from souwen.web.brave_api import BraveApiClient
from souwen.web.search import web_search

__all__ = [
    # 爬虫类（无需 Key）
    "DuckDuckGoClient",
    "YahooClient",
    "BraveClient",
    "GoogleClient",
    "BingClient",
    # API 类（需 Key）
    "SearXNGClient",
    "TavilyClient",
    "ExaClient",
    "SerperClient",
    "BraveApiClient",
    # 聚合搜索
    "web_search",
]
