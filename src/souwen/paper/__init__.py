"""论文数据源模块

包含以下数据源客户端：
- OpenAlexClient: OpenAlex (无需Key)
- SemanticScholarClient: Semantic Scholar (可选Key)
- CrossrefClient: Crossref (无需Key)
- ArxivClient: arXiv (无需Key)
- ArxivFulltextClient: arXiv 论文全文（HTML 优先 + PDF 回退，无需 Key）
- DblpClient: DBLP (无需Key)
- CoreClient: CORE (需Key)
- PubMedClient: PubMed (可选Key)
- UnpaywallClient: Unpaywall (需email)
- HuggingFaceClient: HuggingFace Papers (无需Key，语义搜索 + 社区热度)
- EuropePmcClient: Europe PMC (无需Key)
- PmcClient: PubMed Central (可选Key，复用 PubMed Key)
- DoajClient: DOAJ (可选Key)
- ZenodoClient: Zenodo (可选Token)
- HalClient: HAL (无需Key)
- OpenAireClient: OpenAIRE (可选Key)
- IacrClient: IACR ePrint (无需Key，实验性 HTML 爬虫)
- BioRxivClient: bioRxiv/medRxiv 预印本 (无需Key)
- fetch_pdf: PDF 回退链获取器
"""

from souwen.paper.openalex import OpenAlexClient
from souwen.paper.semantic_scholar import SemanticScholarClient
from souwen.paper.crossref import CrossrefClient
from souwen.paper.arxiv import ArxivClient
from souwen.paper.arxiv_fulltext import ArxivFulltextClient
from souwen.paper.dblp import DblpClient
from souwen.paper.core import CoreClient
from souwen.paper.pubmed import PubMedClient
from souwen.paper.unpaywall import UnpaywallClient
from souwen.paper.pdf_fetcher import fetch_pdf
from souwen.paper.zotero import ZoteroClient
from souwen.paper.huggingface import HuggingFaceClient
from souwen.paper.europepmc import EuropePmcClient
from souwen.paper.pmc import PmcClient
from souwen.paper.doaj import DoajClient
from souwen.paper.zenodo import ZenodoClient
from souwen.paper.hal import HalClient
from souwen.paper.openaire import OpenAireClient
from souwen.paper.iacr import IacrClient
from souwen.paper.biorxiv import BioRxivClient

__all__ = [
    "OpenAlexClient",
    "SemanticScholarClient",
    "CrossrefClient",
    "ArxivClient",
    "ArxivFulltextClient",
    "DblpClient",
    "CoreClient",
    "PubMedClient",
    "UnpaywallClient",
    "fetch_pdf",
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
]
