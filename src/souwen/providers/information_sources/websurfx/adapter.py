from souwen.platform.provider_spec import ScraperSearchProvider


class WebsurfxSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="websurfx", domain="web", enabled=enabled)
