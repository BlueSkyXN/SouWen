from souwen.platform.provider_spec import ScraperSearchProvider


class SearXNGSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="searxng", domain="web", enabled=enabled)
