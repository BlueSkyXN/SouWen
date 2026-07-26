from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

BRAVE_PROVIDER_SPEC = client_scraper_spec(
    "brave", "web", "search.brave.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)
