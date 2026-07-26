from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

DUCKDUCKGO_PROVIDER_SPEC = client_scraper_spec(
    "duckduckgo",
    "web",
    "html.duckduckgo.com",
    "html",
    (HttpOperation(method="POST", endpoint="/html/"),),
)
