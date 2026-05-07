"""Built-in source declarations for this catalog segment."""

from __future__ import annotations

from souwen.registry.sources._helpers import (
    MethodSpec,
    SourceAdapter,
    lazy,
    _reg,
)

# ═════════════════════════════════════════════════════════════
# 13. fetch providers（17 个横切，仅 fetch capability）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="builtin",
        domain="fetch",
        integration="scraper",
        description="内置抓取 (httpx/curl_cffi + trafilatura, 零配置)",
        config_field=None,
        client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
        default_for=frozenset({"fetch:fetch"}),
        package_extra="web",
    )
)

_reg(
    SourceAdapter(
        name="jina_reader",
        domain="fetch",
        integration="open_api",
        description="Jina Reader 内容抓取 (免费, 可选 Key)",
        config_field="jina_api_key",
        needs_config=False,  # Key 可选
        optional_credential_effect="rate_limit",
        client_loader=lazy("souwen.web.jina_reader:JinaReaderClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="arxiv_fulltext",
        domain="fetch",
        integration="open_api",
        description="arXiv 论文全文抓取（按 arxiv.org 论文 URL 提取正文）",
        config_field=None,
        client_loader=lazy("souwen.paper.arxiv_fulltext:ArxivFulltextClient"),
        methods={"fetch": MethodSpec("get_fulltext")},
        package_extra="pdf",
    )
)

_reg(
    SourceAdapter(
        name="crawl4ai",
        domain="fetch",
        integration="scraper",
        description="Crawl4AI 无头浏览器抓取 (本地)",
        config_field=None,
        client_loader=lazy("souwen.web.crawl4ai_fetcher:Crawl4AIFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
        package_extra="crawl4ai",
        risk_level="medium",
        risk_reasons=frozenset({"requires_browser"}),
    )
)

_reg(
    SourceAdapter(
        name="scrapling",
        domain="fetch",
        integration="scraper",
        description="Scrapling 本地抓取 (HTTP/TLS 指纹/动态/Stealth)",
        config_field=None,
        client_loader=lazy("souwen.web.scrapling_fetcher:ScraplingFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
        package_extra="scrapling",
        risk_level="medium",
        risk_reasons=frozenset({"anti_scraping", "requires_browser"}),
        usage_note=(
            "默认使用 HTTP Fetcher；可通过 sources.scrapling.params.mode=dynamic/stealthy "
            "启用浏览器模式"
        ),
    )
)

_reg(
    SourceAdapter(
        name="scrapfly",
        domain="fetch",
        integration="official_api",
        description="Scrapfly JS 渲染 + AI 抽取",
        config_field="scrapfly_api_key",
        client_loader=lazy("souwen.web.scrapfly:ScrapflyClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="diffbot",
        domain="fetch",
        integration="official_api",
        description="Diffbot 结构化文章抽取",
        config_field="diffbot_api_token",
        client_loader=lazy("souwen.web.diffbot:DiffbotClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="scrapingbee",
        domain="fetch",
        integration="official_api",
        description="ScrapingBee 代理 + JS 渲染",
        config_field="scrapingbee_api_key",
        client_loader=lazy("souwen.web.scrapingbee:ScrapingBeeClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="zenrows",
        domain="fetch",
        integration="official_api",
        description="ZenRows 代理 + JS 渲染 + 反爬",
        config_field="zenrows_api_key",
        client_loader=lazy("souwen.web.zenrows:ZenRowsClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="scraperapi",
        domain="fetch",
        integration="official_api",
        description="ScraperAPI 代理池 + JS 渲染",
        config_field="scraperapi_api_key",
        client_loader=lazy("souwen.web.scraperapi:ScraperAPIClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="apify",
        domain="fetch",
        integration="official_api",
        description="Apify Actor 爬虫平台",
        config_field="apify_api_token",
        client_loader=lazy("souwen.web.apify:ApifyClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="cloudflare",
        domain="fetch",
        integration="official_api",
        description="Cloudflare Browser Rendering",
        config_field="cloudflare_api_token",
        credential_fields=("cloudflare_api_token", "cloudflare_account_id"),
        client_loader=lazy("souwen.web.cloudflare_browser:CloudflareBrowserClient"),
        methods={"fetch": MethodSpec("fetch")},
        risk_reasons=frozenset({"quota_cost"}),
    )
)

_reg(
    SourceAdapter(
        name="newspaper",
        domain="fetch",
        integration="scraper",
        description="newspaper4k 文章抽取 (本地)",
        config_field=None,
        client_loader=lazy("souwen.web.newspaper_fetcher:NewspaperFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
        package_extra="newspaper",
    )
)

_reg(
    SourceAdapter(
        name="readability",
        domain="fetch",
        integration="scraper",
        description="Mozilla Readability 算法 (本地)",
        config_field=None,
        client_loader=lazy("souwen.web.readability_fetcher:ReadabilityFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
        package_extra="readability",
    )
)

_reg(
    SourceAdapter(
        name="mcp",
        domain="fetch",
        integration="open_api",
        description="MCP 协议内容抓取 (外部工具)",
        config_field=None,
        client_loader=lazy("souwen.web.mcp_fetch:MCPFetchClient"),
        methods={"fetch": MethodSpec("fetch")},
        package_extra="mcp",
    )
)

_reg(
    SourceAdapter(
        name="site_crawler",
        domain="fetch",
        integration="scraper",
        description="BFS 站点爬虫 (批量多页面)",
        config_field=None,
        client_loader=lazy("souwen.web.site_crawler:SiteCrawlerClient"),
        methods={"fetch": MethodSpec("fetch_batch")},  # 站点爬虫本身就是批量
    )
)

_reg(
    SourceAdapter(
        name="deepwiki",
        domain="fetch",
        integration="open_api",
        description="DeepWiki 开源项目文档抓取 (免费)",
        config_field=None,
        client_loader=lazy("souwen.web.deepwiki:DeepWikiClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)
