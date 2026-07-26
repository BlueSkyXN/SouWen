from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

BING_PROVIDER_SPEC = client_scraper_spec(
    "bing", "web", "www.bing.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)
