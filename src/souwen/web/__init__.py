"""常规网页搜索模块

基于 SoSearch (Rust) 项目移植，提供三个搜索引擎爬虫：
- DuckDuckGoClient: DuckDuckGo HTML 搜索（无需 Key）
- YahooClient: Yahoo 搜索（Bing 驱动）（无需 Key）  
- BraveClient: Brave 独立索引搜索（无需 Key）
- web_search: 并发多引擎聚合搜索
"""

from souwen.web.duckduckgo import DuckDuckGoClient
from souwen.web.yahoo import YahooClient
from souwen.web.brave import BraveClient
from souwen.web.search import web_search

__all__ = [
    "DuckDuckGoClient",
    "YahooClient",
    "BraveClient",
    "web_search",
]
