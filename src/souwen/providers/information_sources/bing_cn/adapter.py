from souwen.platform.provider_spec import ScraperSearchProvider


class BingCnSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="bing_cn", domain="web", enabled=enabled)
