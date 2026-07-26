from souwen.platform.provider_spec import ScraperSearchProvider


class YandexSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="yandex", domain="web", enabled=enabled)
