"""专利数据源模块

包含以下数据源客户端：
- PatentsViewClient: PatentsView/USPTO (API Key)
- EpoOpsClient: EPO OPS (OAuth 2.0)
- UsptoOdpClient: USPTO ODP (API Key)
- GooglePatentsClient: Google Patents (爬虫兜底)
"""

from souwen.providers.runtime_clients.patent.patentsview import PatentsViewClient
from souwen.providers.runtime_clients.patent.epo_ops import EpoOpsClient
from souwen.providers.runtime_clients.patent.uspto_odp import UsptoOdpClient
from souwen.providers.runtime_clients.patent.google_patents import GooglePatentsClient

__all__ = [
    "PatentsViewClient",
    "EpoOpsClient",
    "UsptoOdpClient",
    "GooglePatentsClient",
]
