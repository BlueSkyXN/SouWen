from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

MOJEEK_PROVIDER_SPEC = client_scraper_spec(
    "mojeek", "web", "www.mojeek.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)
