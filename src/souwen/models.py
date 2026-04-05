"""SouWen 统一数据模型（Pydantic v2）

所有数据源的返回结果都必须归一化为这些模型，
确保 AI Agent 获得一致的数据结构。
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    """数据源类型枚举"""

    # 论文数据源
    OPENALEX = "openalex"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    CROSSREF = "crossref"
    ARXIV = "arxiv"
    DBLP = "dblp"
    CORE = "core"
    PUBMED = "pubmed"
    UNPAYWALL = "unpaywall"
    # 专利数据源
    PATENTSVIEW = "patentsview"
    USPTO_ODP = "uspto_odp"
    EPO_OPS = "epo_ops"
    CNIPA = "cnipa"
    THE_LENS = "the_lens"
    PQAI = "pqai"
    PATSNAP = "patsnap"
    GOOGLE_PATENTS = "google_patents"
    # 常规搜索引擎
    WEB_DUCKDUCKGO = "web_duckduckgo"
    WEB_YAHOO = "web_yahoo"
    WEB_BRAVE = "web_brave"
    WEB_GOOGLE = "web_google"
    WEB_BING = "web_bing"
    WEB_SEARXNG = "web_searxng"
    WEB_TAVILY = "web_tavily"
    WEB_EXA = "web_exa"
    WEB_SERPER = "web_serper"
    WEB_BRAVE_API = "web_brave_api"
    # 新增搜索引擎
    WEB_SERPAPI = "web_serpapi"
    WEB_FIRECRAWL = "web_firecrawl"
    WEB_PERPLEXITY = "web_perplexity"
    WEB_LINKUP = "web_linkup"
    WEB_SCRAPINGDOG = "web_scrapingdog"
    WEB_STARTPAGE = "web_startpage"
    WEB_BAIDU = "web_baidu"
    WEB_MOJEEK = "web_mojeek"
    WEB_YANDEX = "web_yandex"
    WEB_WHOOGLE = "web_whoogle"
    WEB_WEBSURFX = "web_websurfx"


class Author(BaseModel):
    """作者信息"""

    name: str
    affiliation: str | None = None
    orcid: str | None = None


class PaperResult(BaseModel):
    """统一论文结果模型"""

    model_config = ConfigDict(extra="forbid")
    source: SourceType
    title: str
    authors: list[Author] = Field(default_factory=list)
    abstract: str | None = None
    doi: str | None = None
    year: int | None = None
    publication_date: date | None = None
    journal: str | None = None
    venue: str | None = None
    citation_count: int | None = None
    open_access_url: str | None = None
    pdf_url: str | None = None
    source_url: str
    tldr: str | None = None  # Semantic Scholar TLDR
    raw: dict = Field(default_factory=dict)


class Applicant(BaseModel):
    """专利申请人/权利人"""

    name: str
    country: str | None = None


class PatentResult(BaseModel):
    """统一专利结果模型"""

    model_config = ConfigDict(extra="forbid")
    source: SourceType
    title: str
    patent_id: str  # 公开号 / 申请号
    application_number: str | None = None
    publication_date: date | None = None
    filing_date: date | None = None
    applicants: list[Applicant] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    claims: str | None = None
    ipc_codes: list[str] = Field(default_factory=list)
    cpc_codes: list[str] = Field(default_factory=list)
    family_id: str | None = None
    legal_status: str | None = None
    pdf_url: str | None = None
    source_url: str
    raw: dict = Field(default_factory=dict)


class WebSearchResult(BaseModel):
    """统一网页搜索结果模型

    统一的网页搜索结果数据模型。
    三个搜索引擎（DuckDuckGo、Yahoo、Brave）的结果
    都归一化为此统一模型。
    """

    source: SourceType
    title: str
    url: str
    snippet: str = ""
    engine: str  # 引擎标识: duckduckgo / yahoo / brave
    raw: dict = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """统一搜索响应"""

    model_config = ConfigDict(extra="forbid")
    query: str
    source: SourceType
    total_results: int | None = None
    results: list[PaperResult] | list[PatentResult] | list[WebSearchResult]
    page: int = 1
    per_page: int = 10


WebSearchResponse = SearchResponse  # 网页搜索使用相同的响应包装


# 所有数据源元信息（CLI 和 API 共用）
ALL_SOURCES: dict[str, list[tuple[str, bool, str]]] = {
    "paper": [
        ("openalex", False, "OpenAlex 开放学术图谱"),
        ("semantic_scholar", False, "Semantic Scholar (可选Key提速)"),
        ("crossref", False, "Crossref DOI 权威源"),
        ("arxiv", False, "arXiv 预印本"),
        ("dblp", False, "DBLP 计算机科学索引"),
        ("core", True, "CORE 全文开放获取"),
        ("pubmed", False, "PubMed 生物医学"),
        ("unpaywall", False, "Unpaywall OA 链接查找"),
    ],
    "patent": [
        ("patentsview", False, "PatentsView/USPTO 美国专利"),
        ("pqai", False, "PQAI 语义专利检索"),
        ("epo_ops", True, "EPO OPS 欧洲专利 (OAuth)"),
        ("uspto_odp", True, "USPTO ODP 官方 API"),
        ("the_lens", True, "The Lens 全球专利+论文"),
        ("cnipa", True, "CNIPA 中国知识产权局 (OAuth)"),
        ("patsnap", True, "PatSnap 智慧芽"),
        ("google_patents", False, "Google Patents (爬虫)"),
    ],
    "web": [
        ("duckduckgo", False, "DuckDuckGo (爬虫)"),
        ("yahoo", False, "Yahoo (爬虫)"),
        ("brave", False, "Brave (爬虫)"),
        ("google", False, "Google (爬虫, 高风险)"),
        ("bing", False, "Bing (爬虫)"),
        ("searxng", False, "SearXNG 元搜索 (需自建)"),
        ("tavily", True, "Tavily AI 搜索"),
        ("exa", True, "Exa 语义搜索"),
        ("serper", True, "Serper Google SERP API"),
        ("brave_api", True, "Brave 官方 API"),
        ("serpapi", True, "SerpAPI 多引擎 SERP"),
        ("firecrawl", True, "Firecrawl 搜索+爬取"),
        ("perplexity", True, "Perplexity Sonar AI 搜索"),
        ("linkup", True, "Linkup 实时搜索"),
        ("scrapingdog", True, "ScrapingDog SERP API"),
        ("startpage", False, "Startpage 隐私搜索 (爬虫)"),
        ("baidu", False, "百度搜索 (爬虫)"),
        ("mojeek", False, "Mojeek 独立搜索 (爬虫)"),
        ("yandex", False, "Yandex 搜索 (爬虫)"),
        ("whoogle", False, "Whoogle Google 代理 (需自建)"),
        ("websurfx", False, "Websurfx 元搜索 (需自建)"),
    ],
}
