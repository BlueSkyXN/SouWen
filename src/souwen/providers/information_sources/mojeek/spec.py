from souwen.platform.provider_spec import HttpOperation, legacy_scraper_spec

MOJEEK_PROVIDER_SPEC = legacy_scraper_spec(
    "mojeek", "web", "www.mojeek.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)
