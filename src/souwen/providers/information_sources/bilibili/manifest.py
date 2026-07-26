from souwen.platform.provider_spec import scraper_search_manifest

BILIBILI_PROVIDER_MANIFEST = scraper_search_manifest(
    "bilibili",
    "BilibiliSearchProvider",
    ["api.bilibili.com"],
    optional_secrets=["BILIBILI_SESSDATA"],
)
