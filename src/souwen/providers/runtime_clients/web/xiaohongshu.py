from __future__ import annotations

from souwen.providers.runtime_clients.web._ddg_site_search import DdgSiteSearchClient


class XiaohongshuClient(DdgSiteSearchClient):
    ENGINE_NAME = "xiaohongshu"
    SITE_DOMAIN = "xiaohongshu.com"
    SOURCE_TYPE = "xiaohongshu"
