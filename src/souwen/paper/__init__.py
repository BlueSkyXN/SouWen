"""论文数据源模块

包含以下数据源客户端：
- OpenAlexClient: OpenAlex (无需Key)
- SemanticScholarClient: Semantic Scholar (可选Key)
- CrossrefClient: Crossref (无需Key)
- ArxivClient: arXiv (无需Key)
- DblpClient: DBLP (无需Key)
- CoreClient: CORE (需Key)
- PubMedClient: PubMed (可选Key)
- UnpaywallClient: Unpaywall (需email)
- fetch_pdf: PDF 回退链获取器
"""

from souwen.paper.openalex import OpenAlexClient
from souwen.paper.semantic_scholar import SemanticScholarClient
from souwen.paper.crossref import CrossrefClient
from souwen.paper.arxiv import ArxivClient
from souwen.paper.dblp import DblpClient
from souwen.paper.core import CoreClient
from souwen.paper.pubmed import PubMedClient
from souwen.paper.unpaywall import UnpaywallClient
from souwen.paper.pdf_fetcher import fetch_pdf

__all__ = [
    "OpenAlexClient",
    "SemanticScholarClient",
    "CrossrefClient",
    "ArxivClient",
    "DblpClient",
    "CoreClient",
    "PubMedClient",
    "UnpaywallClient",
    "fetch_pdf",
]
