from souwen.platform.provider_spec import ScraperSearchProvider


class YahooSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="yahoo", domain="web", enabled=enabled)
