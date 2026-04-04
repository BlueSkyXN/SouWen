"""SouWen 统一数据模型（Pydantic v2）

所有数据源的返回结果都必须归一化为这些模型，
确保 AI Agent 获得一致的数据结构。
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


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


class Author(BaseModel):
    """作者信息"""
    name: str
    affiliation: str | None = None
    orcid: str | None = None


class PaperResult(BaseModel):
    """统一论文结果模型"""
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
    
    移植自 SoSearch (Rust) 项目的 SearchResultItem。
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
    query: str
    source: SourceType
    total_results: int | None = None
    results: list[PaperResult] | list[PatentResult] | list[WebSearchResult]
    page: int = 1
    per_page: int = 10


WebSearchResponse = SearchResponse  # 网页搜索使用相同的响应包装
