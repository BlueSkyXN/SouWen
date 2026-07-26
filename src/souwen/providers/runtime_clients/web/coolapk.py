from __future__ import annotations

from souwen.providers.runtime_clients.web._ddg_site_search import DdgSiteSearchClient


class CoolapkClient(DdgSiteSearchClient):
    ENGINE_NAME = "coolapk"
    SITE_DOMAIN = "coolapk.com"
    SOURCE_TYPE = "coolapk"
