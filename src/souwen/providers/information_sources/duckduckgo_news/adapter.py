from souwen.platform.provider_spec import ScraperSearchProvider


class DuckDuckGoNewsSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="duckduckgo_news", domain="news", enabled=enabled)
