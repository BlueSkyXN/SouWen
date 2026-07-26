from souwen.platform.provider_spec import ScraperSearchProvider


class DuckDuckGoImagesSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="duckduckgo_images", domain="images", enabled=enabled)
