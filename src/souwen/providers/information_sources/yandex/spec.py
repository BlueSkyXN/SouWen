from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

YANDEX_PROVIDER_SPEC = client_scraper_spec(
    "yandex", "web", "yandex.com", "html", (HttpOperation(method="GET", endpoint="/search/"),)
)
