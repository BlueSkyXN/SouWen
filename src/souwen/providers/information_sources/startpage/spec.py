from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

STARTPAGE_PROVIDER_SPEC = client_scraper_spec(
    "startpage",
    "web",
    "www.startpage.com",
    "html",
    (HttpOperation(method="GET", endpoint="/sp/search"),),
)
