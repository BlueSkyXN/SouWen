from souwen.platform.provider_spec import scraper_search_manifest

GOOGLE_PROVIDER_MANIFEST = scraper_search_manifest(
    "google", "GoogleSearchProvider", ["www.google.com"]
)
