"""论文数据源模块"""

from souwen.providers.runtime_clients.paper.openalex import OpenAlexClient
from souwen.providers.runtime_clients.paper.eric import EricClient
from souwen.providers.runtime_clients.paper.osti import OstiClient
from souwen.providers.runtime_clients.paper.crossref import CrossrefClient
from souwen.providers.runtime_clients.paper.arxiv import ArxivClient
from souwen.providers.runtime_clients.paper.arxiv_fulltext import ArxivFulltextClient
from souwen.providers.runtime_clients.paper.pubmed import PubMedClient
from souwen.providers.runtime_clients.paper.huggingface import HuggingFaceClient
from souwen.providers.runtime_clients.paper.europepmc import EuropePmcClient
from souwen.providers.runtime_clients.paper.doaj import DoajClient
from souwen.providers.runtime_clients.paper.zenodo import ZenodoClient
from souwen.providers.runtime_clients.paper.hal import HalClient
from souwen.providers.runtime_clients.paper.openaire import OpenAireClient
from souwen.providers.runtime_clients.paper.iacr import IacrClient

__all__ = [
    "OpenAlexClient",
    "EricClient",
    "OstiClient",
    "CrossrefClient",
    "ArxivClient",
    "ArxivFulltextClient",
    "PubMedClient",
    "HuggingFaceClient",
    "EuropePmcClient",
    "DoajClient",
    "ZenodoClient",
    "HalClient",
    "OpenAireClient",
    "IacrClient",
]
