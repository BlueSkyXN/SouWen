"""专利数据源模块

包含以下数据源客户端：
- PatentsViewClient: PatentsView/USPTO (无需Key)
- PqaiClient: PQAI 语义检索 (无需Key)
- EpoOpsClient: EPO OPS (OAuth 2.0)
- UsptoOdpClient: USPTO ODP (API Key)
- TheLensClient: The Lens (Bearer Token)
- CnipaClient: CNIPA 中国知识产权局 (OAuth 2.0)
- PatSnapClient: PatSnap (API Key)
- GooglePatentsClient: Google Patents (爬虫兜底)
"""

from souwen.patent.patentsview import PatentsViewClient
from souwen.patent.pqai import PqaiClient
from souwen.patent.epo_ops import EpoOpsClient
from souwen.patent.uspto_odp import UsptoOdpClient
from souwen.patent.the_lens import TheLensClient
from souwen.patent.cnipa import CnipaClient
from souwen.patent.patsnap import PatSnapClient
from souwen.patent.google_patents import GooglePatentsClient

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
