from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

GOOGLE_PROVIDER_SPEC = client_scraper_spec(
    "google", "web", "www.google.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)
