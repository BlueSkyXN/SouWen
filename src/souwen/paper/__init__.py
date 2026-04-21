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
- BiorxivClient: bioRxiv (无需Key)
- MedrxivClient: medRxiv (无需Key)
- PmcClient: PubMed Central (可选Key)
- EuropepmcClient: Europe PMC (无需Key)
- ZenodoClient: Zenodo (无需Key)
- IacrClient: IACR ePrint (无需Key)
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
from souwen.paper.biorxiv import BiorxivClient
from souwen.paper.medrxiv import MedrxivClient
from souwen.paper.pmc import PmcClient
from souwen.paper.europepmc import EuropepmcClient
from souwen.paper.zenodo import ZenodoClient
from souwen.paper.iacr import IacrClient
from souwen.paper.pdf_fetcher import fetch_pdf

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
    "BiorxivClient",
    "MedrxivClient",
    "PmcClient",
    "EuropepmcClient",
    "ZenodoClient",
    "IacrClient",
    "fetch_pdf",
]
