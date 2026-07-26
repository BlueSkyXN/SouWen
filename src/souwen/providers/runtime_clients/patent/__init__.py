"""专利数据源模块

包含以下数据源客户端：
- PatentsViewClient: PatentsView/USPTO (API Key)
- PqaiClient: PQAI 语义检索 (API Token)
- EpoOpsClient: EPO OPS (OAuth 2.0)
- UsptoOdpClient: USPTO ODP (API Key)
- TheLensClient: The Lens (Bearer Token)
- CnipaClient: CNIPA 中国知识产权局 (OAuth 2.0)
- PatSnapClient: PatSnap (API Key)
- GooglePatentsClient: Google Patents (爬虫兜底)
"""

from souwen.providers.runtime_clients.patent.patentsview import PatentsViewClient
from souwen.providers.runtime_clients.patent.pqai import PqaiClient
from souwen.providers.runtime_clients.patent.epo_ops import EpoOpsClient
from souwen.providers.runtime_clients.patent.uspto_odp import UsptoOdpClient
from souwen.providers.runtime_clients.patent.the_lens import TheLensClient
from souwen.providers.runtime_clients.patent.cnipa import CnipaClient
from souwen.providers.runtime_clients.patent.patsnap import PatSnapClient
from souwen.providers.runtime_clients.patent.google_patents import GooglePatentsClient

__all__ = [
    "PatentsViewClient",
    "PqaiClient",
    "EpoOpsClient",
    "UsptoOdpClient",
    "TheLensClient",
    "CnipaClient",
    "PatSnapClient",
    "GooglePatentsClient",
]
