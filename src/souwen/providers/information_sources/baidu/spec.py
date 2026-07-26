from souwen.platform.provider_spec import HttpOperation, legacy_scraper_spec

BAIDU_PROVIDER_SPEC = legacy_scraper_spec(
    "baidu", "web", "www.baidu.com", "html", (HttpOperation(method="GET", endpoint="/s"),)
)
