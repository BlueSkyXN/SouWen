from souwen.platform.provider_spec import ScraperSearchProvider


class DuckDuckGoVideosSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="duckduckgo_videos", domain="videos", enabled=enabled)
