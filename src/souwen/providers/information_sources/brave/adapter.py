from souwen.platform.provider_spec import ScraperSearchProvider


class BraveSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="brave", domain="web", enabled=enabled)
