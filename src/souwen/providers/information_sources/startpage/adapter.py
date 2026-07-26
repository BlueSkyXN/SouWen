from souwen.platform.provider_spec import ScraperSearchProvider


class StartpageSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="startpage", domain="web", enabled=enabled)
