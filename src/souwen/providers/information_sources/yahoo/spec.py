from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

YAHOO_PROVIDER_SPEC = client_scraper_spec(
    "yahoo", "web", "search.yahoo.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)
