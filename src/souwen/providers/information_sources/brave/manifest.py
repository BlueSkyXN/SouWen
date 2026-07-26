from souwen.platform.provider_spec import scraper_search_manifest

BRAVE_PROVIDER_MANIFEST = scraper_search_manifest(
    "brave", "BraveSearchProvider", ["search.brave.com"]
)
