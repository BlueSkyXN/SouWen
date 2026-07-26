from souwen.platform.provider_spec import HttpOperation, legacy_scraper_spec

DUCKDUCKGO_NEWS_PROVIDER_SPEC = legacy_scraper_spec(
    "duckduckgo_news",
    "news",
    "duckduckgo.com",
    "multi_transport",
    (HttpOperation(method="GET", endpoint="/"), HttpOperation(method="GET", endpoint="/news.js")),
)
