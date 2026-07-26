from souwen.platform.provider_spec import scraper_search_manifest

YAHOO_PROVIDER_MANIFEST = scraper_search_manifest(
    "yahoo", "YahooSearchProvider", ["search.yahoo.com"]
)
