from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

DUCKDUCKGO_IMAGES_PROVIDER_SPEC = client_scraper_spec(
    "duckduckgo_images",
    "images",
    "duckduckgo.com",
    "multi_transport",
    (HttpOperation(method="GET", endpoint="/"), HttpOperation(method="GET", endpoint="/i.js")),
)
