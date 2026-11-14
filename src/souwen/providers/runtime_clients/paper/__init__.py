"""历史导入路径转发：各源 client 已并入 information_sources/fetch_sources 的 source.py。"""

from __future__ import annotations

from souwen.providers.information_sources.openalex.source import OpenAlexClient  # noqa: F401
from souwen.providers.information_sources.eric.source import EricClient  # noqa: F401
from souwen.providers.information_sources.arxiv.source import ArxivClient  # noqa: F401
from souwen.providers.information_sources.crossref.source import CrossrefClient  # noqa: F401
from souwen.providers.information_sources.europepmc.source import EuropePmcClient  # noqa: F401
from souwen.providers.information_sources.hal.source import HalClient  # noqa: F401
from souwen.providers.information_sources.huggingface.source import HuggingFaceClient  # noqa: F401
from souwen.providers.information_sources.iacr.source import IacrClient  # noqa: F401
from souwen.providers.information_sources.osti.source import OstiClient  # noqa: F401
from souwen.providers.information_sources.pubmed.source import PubMedClient  # noqa: F401
from souwen.providers.information_sources.doaj.source import DoajClient  # noqa: F401
from souwen.providers.information_sources.openaire.source import OpenAireClient  # noqa: F401
from souwen.providers.information_sources.zenodo.source import ZenodoClient  # noqa: F401
from souwen.providers.fetch_sources.arxiv_fulltext.source import ArxivFulltextClient  # noqa: F401

__all__ = [
    "OpenAlexClient",
    "EricClient",
    "ArxivClient",
    "CrossrefClient",
    "EuropePmcClient",
    "HalClient",
    "HuggingFaceClient",
    "IacrClient",
    "OstiClient",
    "PubMedClient",
    "DoajClient",
    "OpenAireClient",
    "ZenodoClient",
    "ArxivFulltextClient",
]
