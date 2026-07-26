from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

DUCKDUCKGO_VIDEOS_PROVIDER_SPEC = client_scraper_spec(
    "duckduckgo_videos",
    "videos",
    "duckduckgo.com",
    "multi_transport",
    (HttpOperation(method="GET", endpoint="/"), HttpOperation(method="GET", endpoint="/v.js")),
)
