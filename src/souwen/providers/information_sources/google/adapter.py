from souwen.platform.provider_spec import ScraperSearchProvider


class GoogleSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="google", domain="web", enabled=enabled)
