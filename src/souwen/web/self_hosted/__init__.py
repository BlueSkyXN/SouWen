"""web/self_hosted/ — 自托管元搜索（v1）

3 个：searxng / whoogle / websurfx
"""

from souwen.web.searxng import SearXNGClient
from souwen.web.websurfx import WebsurfxClient
from souwen.web.whoogle import WhoogleClient

__all__ = ["SearXNGClient", "WhoogleClient", "WebsurfxClient"]
