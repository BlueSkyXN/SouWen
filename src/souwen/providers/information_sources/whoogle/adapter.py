from souwen.platform.provider_spec import ScraperSearchProvider


class WhoogleSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="whoogle", domain="web", enabled=enabled)
