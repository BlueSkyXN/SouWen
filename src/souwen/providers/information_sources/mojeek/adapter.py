from souwen.platform.provider_spec import ScraperSearchProvider


class MojeekSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="mojeek", domain="web", enabled=enabled)
