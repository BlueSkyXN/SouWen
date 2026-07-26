from souwen.platform.provider_spec import AuthDeclaration, HttpOperation, legacy_scraper_spec

BILIBILI_PROVIDER_SPEC = legacy_scraper_spec(
    "bilibili",
    "videos",
    "api.bilibili.com",
    "multi_transport",
    (
        HttpOperation(method="GET", endpoint="/x/web-interface/nav"),
        HttpOperation(method="GET", endpoint="/x/web-interface/search/type"),
    ),
    auth=AuthDeclaration(
        placement="header", reference="BILIBILI_SESSDATA", field_name="Cookie", required=False
    ),
)
