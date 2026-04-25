from __future__ import annotations

from souwen.models import SourceType
from souwen.web._ddg_site_search import DdgSiteSearchClient


class CoolapkClient(DdgSiteSearchClient):
    ENGINE_NAME = "coolapk"
    SITE_DOMAIN = "coolapk.com"
    SOURCE_TYPE = SourceType.WEB_COOLAPK
