from souwen.platform.provider_spec import HttpOperation, client_scraper_spec

BAIDU_PROVIDER_SPEC = client_scraper_spec(
    "baidu", "web", "www.baidu.com", "html", (HttpOperation(method="GET", endpoint="/s"),)
)
