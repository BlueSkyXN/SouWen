from souwen.platform.provider_spec import HttpOperation, legacy_scraper_spec

BING_PROVIDER_SPEC = legacy_scraper_spec(
    "bing", "web", "www.bing.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)
