from souwen.platform.provider_spec import HttpOperation, legacy_scraper_spec

BRAVE_PROVIDER_SPEC = legacy_scraper_spec(
    "brave", "web", "search.brave.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)
