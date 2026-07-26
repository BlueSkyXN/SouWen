"""论文数据源模块

包含以下数据源客户端：
- OpenAlexClient: OpenAlex (可匿名使用；可选 API Key 提高每日预算)
- EricClient: ERIC 教育研究元数据（官方匿名 API）
- OstiClient: OSTI.GOV 能源科研记录（官方匿名 API）
- SemanticScholarClient: Semantic Scholar (可选Key)
- CrossrefClient: Crossref (无需Key)
- ArxivClient: arXiv (无需Key)
- ArxivFulltextClient: arXiv 论文 HTML 全文（无需 Key）
- DblpClient: DBLP (无需Key)
- CoreClient: CORE (需Key)
- PubMedClient: PubMed (可选Key)
- HuggingFaceClient: HuggingFace Papers (无需Key，语义搜索 + 社区热度)
- EuropePmcClient: Europe PMC (无需Key)
- PmcClient: PubMed Central (可选Key，复用 PubMed Key)
- DoajClient: DOAJ (可选Key)
- ZenodoClient: Zenodo (可选Token)
- HalClient: HAL (无需Key)
- OpenAireClient: OpenAIRE (可选Key)
- IacrClient: IACR ePrint (无需Key，实验性 HTML 爬虫)
- BioRxivClient: bioRxiv/medRxiv 预印本 (无需Key)
- IeeeXploreClient: IEEE Xplore (需Key)
"""

from souwen.providers.runtime_clients.paper.openalex import OpenAlexClient
from souwen.providers.runtime_clients.paper.eric import EricClient
from souwen.providers.runtime_clients.paper.osti import OstiClient
from souwen.providers.runtime_clients.paper.semantic_scholar import SemanticScholarClient
from souwen.providers.runtime_clients.paper.crossref import CrossrefClient
from souwen.providers.runtime_clients.paper.arxiv import ArxivClient
from souwen.providers.runtime_clients.paper.arxiv_fulltext import ArxivFulltextClient
from souwen.providers.runtime_clients.paper.dblp import DblpClient
from souwen.providers.runtime_clients.paper.core import CoreClient
from souwen.providers.runtime_clients.paper.pubmed import PubMedClient
from souwen.providers.runtime_clients.paper.zotero import ZoteroClient
from souwen.providers.runtime_clients.paper.huggingface import HuggingFaceClient
from souwen.providers.runtime_clients.paper.europepmc import EuropePmcClient
from souwen.providers.runtime_clients.paper.pmc import PmcClient
from souwen.providers.runtime_clients.paper.doaj import DoajClient
from souwen.providers.runtime_clients.paper.zenodo import ZenodoClient
from souwen.providers.runtime_clients.paper.hal import HalClient
from souwen.providers.runtime_clients.paper.openaire import OpenAireClient
from souwen.providers.runtime_clients.paper.iacr import IacrClient
from souwen.providers.runtime_clients.paper.biorxiv import BioRxivClient
from souwen.providers.runtime_clients.paper.ieee_xplore import IeeeXploreClient

__all__ = [
    "OpenAlexClient",
    "EricClient",
    "OstiClient",
    "SemanticScholarClient",
    "CrossrefClient",
    "ArxivClient",
    "ArxivFulltextClient",
    "DblpClient",
    "CoreClient",
    "PubMedClient",
    "ZoteroClient",
    "HuggingFaceClient",
    "EuropePmcClient",
    "PmcClient",
    "DoajClient",
    "ZenodoClient",
    "HalClient",
    "OpenAireClient",
    "IacrClient",
    "BioRxivClient",
    "IeeeXploreClient",
]
