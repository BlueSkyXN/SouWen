"""web/api/ — 授权商业搜索 API（v1）

13 个：tavily / exa / serper / serpapi / brave_api / firecrawl / perplexity /
linkup / xcrawl / scrapingdog / metaso / zhipuai / aliyun_iqs。
"""

from souwen.web.aliyun_iqs import AliyunIQSClient
from souwen.web.brave_api import BraveApiClient
from souwen.web.exa import ExaClient
from souwen.web.firecrawl import FirecrawlClient
from souwen.web.linkup import LinkupClient
from souwen.web.metaso import MetasoClient
from souwen.web.perplexity import PerplexityClient
from souwen.web.scrapingdog import ScrapingDogClient
from souwen.web.serpapi import SerpApiClient
from souwen.web.serper import SerperClient
from souwen.web.tavily import TavilyClient
from souwen.web.xcrawl import XCrawlClient
from souwen.web.zhipuai_search import ZhipuAISearchClient

__all__ = [
    "TavilyClient",
    "ExaClient",
    "SerperClient",
    "SerpApiClient",
    "BraveApiClient",
    "FirecrawlClient",
    "PerplexityClient",
    "LinkupClient",
    "XCrawlClient",
    "ScrapingDogClient",
    "MetasoClient",
    "ZhipuAISearchClient",
    "AliyunIQSClient",
]
