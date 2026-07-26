from souwen.platform.provider_spec import scraper_search_manifest

DUCKDUCKGO_PROVIDER_MANIFEST = scraper_search_manifest(
    "duckduckgo", "DuckDuckGoSearchProvider", ["html.duckduckgo.com"]
)
