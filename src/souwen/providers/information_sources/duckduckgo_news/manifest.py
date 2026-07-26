from souwen.platform.provider_spec import scraper_search_manifest

DUCKDUCKGO_NEWS_PROVIDER_MANIFEST = scraper_search_manifest(
    "duckduckgo_news", "DuckDuckGoNewsSearchProvider", ["duckduckgo.com"]
)
