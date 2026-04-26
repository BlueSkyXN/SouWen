from __future__ import annotations

from souwen.models import SourceType
from souwen.web._ddg_site_search import DdgSiteSearchClient


class NodeSeekClient(DdgSiteSearchClient):
    ENGINE_NAME = "nodeseek"
    SITE_DOMAIN = "nodeseek.com"
    SOURCE_TYPE = SourceType.WEB_NODESEEK
