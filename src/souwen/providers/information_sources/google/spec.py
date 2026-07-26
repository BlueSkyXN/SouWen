from souwen.platform.provider_spec import HttpOperation, legacy_scraper_spec

GOOGLE_PROVIDER_SPEC = legacy_scraper_spec(
    "google", "web", "www.google.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)
