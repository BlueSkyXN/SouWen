from __future__ import annotations

from souwen.web._ddg_site_search import DdgSiteSearchClient


class V2EXClient(DdgSiteSearchClient):
    ENGINE_NAME = "v2ex"
    SITE_DOMAIN = "v2ex.com"
    SOURCE_TYPE = "v2ex"
