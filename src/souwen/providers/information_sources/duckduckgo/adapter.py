from souwen.platform.provider_spec import ScraperSearchProvider


class DuckDuckGoSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="duckduckgo", domain="web", enabled=enabled)
