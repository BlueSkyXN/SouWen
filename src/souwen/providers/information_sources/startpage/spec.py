from souwen.platform.provider_spec import HttpOperation, legacy_scraper_spec

STARTPAGE_PROVIDER_SPEC = legacy_scraper_spec(
    "startpage",
    "web",
    "www.startpage.com",
    "html",
    (HttpOperation(method="GET", endpoint="/sp/search"),),
)
