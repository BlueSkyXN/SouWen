"""fetch/providers/ — 抓取提供者实现

Public API: re-export 各 fetch 客户端，保持 import 路径稳定。
"""

from souwen.web.apify import ApifyClient
from souwen.web.builtin import BuiltinFetcherClient
from souwen.web.cloudflare_browser import CloudflareBrowserClient
from souwen.web.crawl4ai_fetcher import Crawl4AIFetcherClient
from souwen.web.deepwiki import DeepWikiClient
from souwen.web.diffbot import DiffbotClient
from souwen.web.jina_reader import JinaReaderClient
from souwen.web.mcp_fetch import MCPFetchClient
from souwen.web.newspaper_fetcher import NewspaperFetcherClient
from souwen.web.readability_fetcher import ReadabilityFetcherClient
from souwen.web.scraperapi import ScraperAPIClient
from souwen.web.scrapfly import ScrapflyClient
from souwen.web.scrapingbee import ScrapingBeeClient
from souwen.web.site_crawler import SiteCrawlerClient
from souwen.web.zenrows import ZenRowsClient

__all__ = [
    "BuiltinFetcherClient",
    "JinaReaderClient",
    "Crawl4AIFetcherClient",
    "NewspaperFetcherClient",
    "ReadabilityFetcherClient",
    "SiteCrawlerClient",
    "MCPFetchClient",
    "DeepWikiClient",
    "ScrapflyClient",
    "DiffbotClient",
    "ScrapingBeeClient",
    "ZenRowsClient",
    "ScraperAPIClient",
    "ApifyClient",
    "CloudflareBrowserClient",
]
