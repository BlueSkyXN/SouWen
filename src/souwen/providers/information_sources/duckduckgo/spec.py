from souwen.platform.provider_spec import HttpOperation, legacy_scraper_spec

DUCKDUCKGO_PROVIDER_SPEC = legacy_scraper_spec(
    "duckduckgo",
    "web",
    "html.duckduckgo.com",
    "html",
    (HttpOperation(method="POST", endpoint="/html/"),),
)
