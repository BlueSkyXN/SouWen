from souwen.platform.provider_spec import ScraperSearchProvider


class BingSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="bing", domain="web", enabled=enabled)
