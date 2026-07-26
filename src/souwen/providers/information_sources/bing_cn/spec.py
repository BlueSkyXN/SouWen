from souwen.platform.provider_spec import HttpOperation, legacy_scraper_spec

BING_CN_PROVIDER_SPEC = legacy_scraper_spec(
    "bing_cn", "web", "cn.bing.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)
