from __future__ import annotations

from souwen.models import SourceType
from souwen.web._ddg_site_search import DdgSiteSearchClient


class HostLocClient(DdgSiteSearchClient):
    ENGINE_NAME = "hostloc"
    SITE_DOMAIN = "hostloc.com"
    SOURCE_TYPE = SourceType.WEB_HOSTLOC
