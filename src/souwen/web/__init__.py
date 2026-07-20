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
- FeishuDriveClient: 飞书云文档搜索（需 App ID + App Secret）

API 类（需 Key / 自建实例）：
- SearXNGClient: SearXNG 元搜索（250+ 引擎）
- TavilyClient: Tavily AI 搜索（为 Agent 设计）
- ExaClient: Exa 语义搜索（神经索引）
- SerperClient: Serper Google SERP API
- BraveApiClient: Brave 官方 API
- MetasoClient: 秘塔搜索（文档/网页/学术三种范围）
- XCrawlClient: XCrawl 搜索+抓取
- ZhipuAISearchClient: 智谱 AI Web Search Pro（含 AI 摘要，中英文友好）
- AliyunIQSClient: 阿里云 IQS 通义晓搜（含 AI 摘要，中英文友好）
- KimiCodeClient: Kimi Code 搜索+网页获取

内容抓取（fetch 提供者）：
- SiteCrawlerClient: 多页 BFS 站点爬虫（参照 deepwiki-mcp httpCrawler.ts，零配置）
- DeepWikiClient: DeepWiki GitHub 仓库文档抓取（参照 deepwiki-mcp，零配置）

辅助函数：
- crawl_site(): 便捷 BFS 爬取函数
- resolve_github_repo(): 将库名解析为 owner/repo（GitHub Search API）

聚合搜索：
- web_search(): 并发多引擎聚合 + URL 去重
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "DuckDuckGoClient": ("souwen.web.duckduckgo", "DuckDuckGoClient"),
    "DuckDuckGoNewsClient": ("souwen.web.ddg_news", "DuckDuckGoNewsClient"),
    "DuckDuckGoImagesClient": ("souwen.web.ddg_images", "DuckDuckGoImagesClient"),
    "ImageSearchResult": ("souwen.web.ddg_images", "ImageSearchResult"),
    "ImageSearchResponse": ("souwen.web.ddg_images", "ImageSearchResponse"),
    "DuckDuckGoVideosClient": ("souwen.web.ddg_videos", "DuckDuckGoVideosClient"),
    "VideoSearchResult": ("souwen.web.ddg_videos", "VideoSearchResult"),
    "VideoSearchResponse": ("souwen.web.ddg_videos", "VideoSearchResponse"),
    "YahooClient": ("souwen.web.yahoo", "YahooClient"),
    "BraveClient": ("souwen.web.brave", "BraveClient"),
    "GoogleClient": ("souwen.web.google", "GoogleClient"),
    "BingClient": ("souwen.web.bing", "BingClient"),
    "BingCnClient": ("souwen.web.bing_cn", "BingCnClient"),
    "StartpageClient": ("souwen.web.startpage", "StartpageClient"),
    "BaiduClient": ("souwen.web.baidu", "BaiduClient"),
    "MojeekClient": ("souwen.web.mojeek", "MojeekClient"),
    "YandexClient": ("souwen.web.yandex", "YandexClient"),
    "SearXNGClient": ("souwen.web.searxng", "SearXNGClient"),
    "TavilyClient": ("souwen.web.tavily", "TavilyClient"),
    "ExaClient": ("souwen.web.exa", "ExaClient"),
    "SerperClient": ("souwen.web.serper", "SerperClient"),
    "BraveApiClient": ("souwen.web.brave_api", "BraveApiClient"),
    "SerpApiClient": ("souwen.web.serpapi", "SerpApiClient"),
    "FirecrawlClient": ("souwen.web.firecrawl", "FirecrawlClient"),
    "XCrawlClient": ("souwen.web.xcrawl", "XCrawlClient"),
    "PerplexityClient": ("souwen.web.perplexity", "PerplexityClient"),
    "LinkupClient": ("souwen.web.linkup", "LinkupClient"),
    "ScrapingDogClient": ("souwen.web.scrapingdog", "ScrapingDogClient"),
    "WhoogleClient": ("souwen.web.whoogle", "WhoogleClient"),
    "WebsurfxClient": ("souwen.web.websurfx", "WebsurfxClient"),
    "GitHubClient": ("souwen.web.github", "GitHubClient"),
    "StackOverflowClient": ("souwen.web.stackoverflow", "StackOverflowClient"),
    "RedditClient": ("souwen.web.reddit", "RedditClient"),
    "BilibiliClient": ("souwen.web.bilibili", "BilibiliClient"),
    "WikipediaClient": ("souwen.web.wikipedia", "WikipediaClient"),
    "YouTubeClient": ("souwen.web.youtube", "YouTubeClient"),
    "VideoDetail": ("souwen.web.youtube", "VideoDetail"),
    "ZhihuClient": ("souwen.web.zhihu", "ZhihuClient"),
    "WeiboClient": ("souwen.web.weibo", "WeiboClient"),
    "CSDNClient": ("souwen.web.csdn", "CSDNClient"),
    "JuejinClient": ("souwen.web.juejin", "JuejinClient"),
    "LinuxDoClient": ("souwen.web.linuxdo", "LinuxDoClient"),
    "NodeSeekClient": ("souwen.web.nodeseek", "NodeSeekClient"),
    "HostLocClient": ("souwen.web.hostloc", "HostLocClient"),
    "V2EXClient": ("souwen.web.v2ex", "V2EXClient"),
    "CoolapkClient": ("souwen.web.coolapk", "CoolapkClient"),
    "XiaohongshuClient": ("souwen.web.xiaohongshu", "XiaohongshuClient"),
    "CommunityCnClient": ("souwen.web.community_cn", "CommunityCnClient"),
    "TwitterClient": ("souwen.web.twitter", "TwitterClient"),
    "FacebookClient": ("souwen.web.facebook", "FacebookClient"),
    "FeishuDriveClient": ("souwen.web.feishu_drive", "FeishuDriveClient"),
    "MetasoClient": ("souwen.web.metaso", "MetasoClient"),
    "ZhipuAISearchClient": ("souwen.web.zhipuai_search", "ZhipuAISearchClient"),
    "AliyunIQSClient": ("souwen.web.aliyun_iqs", "AliyunIQSClient"),
    "KimiCodeClient": ("souwen.web.kimi_code", "KimiCodeClient"),
    "JinaReaderClient": ("souwen.web.jina_reader", "JinaReaderClient"),
    "BuiltinFetcherClient": ("souwen.web.builtin", "BuiltinFetcherClient"),
    "WaybackClient": ("souwen.web.wayback", "WaybackClient"),
    "MCPClient": ("souwen.web.mcp_client", "MCPClient"),
    "MCPFetchClient": ("souwen.web.mcp_fetch", "MCPFetchClient"),
    "SiteCrawlerClient": ("souwen.web.site_crawler", "SiteCrawlerClient"),
    "crawl_site": ("souwen.web.site_crawler", "crawl_site"),
    "DeepWikiClient": ("souwen.web.deepwiki", "DeepWikiClient"),
    "resolve_github_repo": ("souwen.web.deepwiki", "resolve_github_repo"),
    "web_search": ("souwen.web.search", "web_search"),
    "fetch_content": ("souwen.web.fetch", "fetch_content"),
}


def __getattr__(name: str) -> Any:
    """按需加载兼容的 ``souwen.web`` convenience exports。"""

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
    "TavilyClient",
    "ExaClient",
    "SerperClient",
    "BraveApiClient",
    "SerpApiClient",
    "FirecrawlClient",
    "XCrawlClient",
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
    "VideoDetail",
    "ZhihuClient",
    "WeiboClient",
    # 中文技术社区
    "CSDNClient",
    "JuejinClient",
    "LinuxDoClient",
    "NodeSeekClient",
    "HostLocClient",
    "V2EXClient",
    "CoolapkClient",
    "XiaohongshuClient",
    "CommunityCnClient",
    # 国际社交媒体（官方 API）
    "TwitterClient",
    "FacebookClient",
    # 办公/企业平台（官方 API）
    "FeishuDriveClient",
    # API 类（需 Key）- 中文搜索
    "MetasoClient",
    "ZhipuAISearchClient",
    "AliyunIQSClient",
    "KimiCodeClient",
    # 内容抓取类 (fetch)
    "BuiltinFetcherClient",
    "JinaReaderClient",
    "WaybackClient",
    # MCP 客户端
    "MCPClient",
    "MCPFetchClient",
    # 站点爬虫 + DeepWiki
    "SiteCrawlerClient",
    "crawl_site",
    "DeepWikiClient",
    "resolve_github_repo",
    # 聚合搜索/抓取
    "web_search",
    "fetch_content",
]
