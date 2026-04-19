"""SouWen 统一数据模型（Pydantic v2）

文件用途：
    定义所有数据源返回结果的统一 Pydantic 数据模型，确保 AI Agent 获得一致的数据结构。
    支持论文、专利、网页三大类结果以及统一的 SearchResponse 容器，
    所有模型采用 ConfigDict(extra="allow") 兼容上游字段扩展。

类清单（[已修正] 与实际定义对齐）：
    SourceType（str, Enum）
        - 功能：所有数据源的字符串枚举（论文 / 专利 / Web）
        - 论文：openalex / semantic_scholar / crossref / arxiv / dblp / core / pubmed / unpaywall
        - 专利：patents_view / pqai / epo_ops / uspto_odp / the_lens / cnipa / patsnap / google_patents
        - Web：google / bing / duckduckgo / yahoo / brave / startpage / baidu / mojeek / yandex /
              searxng / whoogle / websurfx / tavily / exa / serper / brave_api / serpapi /
              firecrawl / perplexity / linkup / scrapingdog

    Author（BaseModel）
        - 功能：论文作者
        - 字段：name (必填), affiliation, orcid

    PaperResult（BaseModel）
        - 功能：单篇论文的统一模型
        - 关键字段：source (SourceType), title, authors (list[Author]), abstract,
                  doi, year, publication_date (date), venue, citation_count,
                  url, pdf_url, raw (原始响应)
        - 校验器：_normalize_publication_date 通过 _coerce_date 容错解析

    Applicant（BaseModel）
        - 功能：专利申请人/受让人
        - 字段：name (必填), country

    PatentResult（BaseModel）
        - 功能：单件专利的统一模型
        - 关键字段：source, patent_id (必填), title, abstract, applicants (list[Applicant]),
                  inventors (list[str]), filing_date, publication_date, ipc_codes,
                  url, raw
        - 校验器：_normalize_dates 同时归一化 filing_date 与 publication_date

    WebSearchResult（BaseModel）
        - 功能：单条网页搜索结果
        - 字段：title (必填), url (必填), snippet, source (SourceType), engine,
                rank (排序位次), published_date, raw

    SearchResponse（BaseModel）
        - 功能：单一数据源的搜索响应容器
        - 字段：source (SourceType), query, total_count, results (list[Any]),
                fetched_at (datetime, 默认 utcnow), error
        - 用途：search_papers / search_patents / web_search 的统一返回单元

辅助函数：
    _coerce_date(value) — 宽松日期归一化
        接受：None / datetime / date / ISO 字符串（YYYY-MM-DD 或带时间）
        无法解析时返回 None（不抛异常）

Pydantic 配置策略：
    - ConfigDict(extra="allow")：兼容上游响应中的未声明字段
    - field_validator(..., mode="before")：在字段赋值前调用 _coerce_date 容错

模块依赖：
    - pydantic v2: 数据验证和序列化
    - datetime: 日期时间处理
    - enum: 枚举类型
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _coerce_date(value):
    """宽松日期归一化

    将多种日期格式统一为 date 对象，或返回 None（无效值时）。

    支持格式：
        - None / 空字符串 → None
        - datetime 对象 → date
        - date 对象 → date（保持不变）
        - ISO 日期字符串 (YYYY-MM-DD) → date
        - ISO 时间戳 (YYYY-MM-DDTHH:MM:SS...) → 提取日期部分

    Args:
        value: 待转换的日期值

    Returns:
        date 对象或 None

    Note:
        无法解析的值返回 None，不抛异常（宽松验证）
    """
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if "T" in text:
            text = text.split("T", 1)[0]
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    return None


class SourceType(str, Enum):
    """数据源类型枚举

    分为三大类：
    - 论文源：OpenAlex, Semantic Scholar, CrossRef, arXiv, DBLP, CORE, PubMed, Unpaywall, IEEE
    - 专利源：PatentsView, USPTO ODP, EPO OPS, CNIPA, Lens, PatSnap
    - Web 源：Google, DuckDuckGo, Tavily, Serper, Brave Search, Exa 等
    """

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
    # 社交/平台搜索
    WEB_GITHUB = "web_github"
    WEB_STACKOVERFLOW = "web_stackoverflow"
    WEB_REDDIT = "web_reddit"
    WEB_BILIBILI = "web_bilibili"
    WEB_WIKIPEDIA = "web_wikipedia"
    WEB_YOUTUBE = "web_youtube"
    WEB_ZHIHU = "web_zhihu"
    WEB_WEIBO = "web_weibo"
    # ── 内容抓取 (fetch) ──
    FETCH_JINA_READER = "fetch_jina_reader"


class Author(BaseModel):
    """作者信息

    Attributes:
        name: 作者姓名
        affiliation: 所属机构（可选）
        orcid: ORCID 标识符（可选）
    """

    name: str
    affiliation: str | None = None
    orcid: str | None = None


class PaperResult(BaseModel):
    """统一论文结果模型

    所有论文数据源的结果都应归一化为此格式。支持部分字段缺失（None）。

    Attributes:
        source: 数据源类型（SourceType 枚举）
        title: 论文标题
        authors: 作者列表（Author 对象）
        abstract: 摘要文本（可选）
        doi: DOI 标识符（可选）
        year: 发表年份（整数）
        publication_date: 发表日期（ISO 日期对象）
        journal: 期刊名称（可选）
        venue: 会议/期刊场地（可选）
        citation_count: 被引用次数（可选）
        open_access_url: 开源获取 URL（可选）
        pdf_url: PDF 链接（可选）
        source_url: 原数据源的论文 URL
        tldr: 论文 TL;DR 摘要（Semantic Scholar 特有）
        raw: 原始 API 响应字段（用于调试）
    """

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

    @field_validator("publication_date", mode="before")
    @classmethod
    def _normalize_publication_date(cls, value):
        """字段前处理：日期字段宽松归一化"""
        return _coerce_date(value)


class Applicant(BaseModel):
    """专利申请人/权利人

    Attributes:
        name: 申请人/权利人名称
        country: 所属国家代码或名称（可选）
    """

    name: str
    country: str | None = None


class PatentResult(BaseModel):
    """统一专利结果模型

    所有专利数据源的结果都应归一化为此格式。支持部分字段缺失。

    Attributes:
        source: 数据源类型（SourceType 枚举）
        title: 专利名称/标题
        patent_id: 公开号或申请号
        application_number: 申请号（若与 patent_id 不同）
        publication_date: 公布/发布日期（ISO 日期对象）
        filing_date: 申请日期（ISO 日期对象）
        applicants: 申请人/权利人列表（Applicant 对象）
        inventors: 发明人列表（名称字符串）
        abstract: 摘要文本（可选）
        claims: 权利要求书（可选）
        ipc_codes: IPC 分类码列表（国际专利分类）
        cpc_codes: CPC 分类码列表（合作专利分类）
        family_id: 专利族 ID（可选）
        legal_status: 法律状态（如"授权"、"放弃"等）
    """

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

    @field_validator("publication_date", "filing_date", mode="before")
    @classmethod
    def _normalize_dates(cls, value):
        return _coerce_date(value)


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


# ── 内容抓取模型 (Fetch / Extract) ─────────────────────────

class FetchResult(BaseModel):
    """单个 URL 的内容抓取结果"""

    url: str
    final_url: str  # 重定向后的最终 URL（无重定向时与 url 相同）
    title: str = ""
    content: str = ""  # 提取的正文（优先 markdown）
    content_format: Literal["markdown", "text", "html"] = "markdown"
    source: str = ""  # 提供者标识: jina_reader / tavily / firecrawl / exa / builtin
    snippet: str = ""  # 截断的摘要（前 500 字）
    published_date: str | None = None
    author: str | None = None
    error: str | None = None
    raw: dict = Field(default_factory=dict)


class FetchResponse(BaseModel):
    """内容抓取聚合响应"""

    model_config = ConfigDict(extra="forbid")
    urls: list[str]
    results: list[FetchResult]
    total: int = 0
    total_ok: int = 0
    total_failed: int = 0
    provider: str = ""
    meta: dict = Field(default_factory=dict)
ALL_SOURCES: dict[str, list[tuple[str, bool, str]]] = {
    "paper": [
        ("openalex", False, "OpenAlex 开放学术图谱"),
        ("semantic_scholar", False, "Semantic Scholar（免 Key 可试用，但易限流）"),
        ("crossref", False, "Crossref DOI 权威源"),
        ("arxiv", False, "arXiv 预印本"),
        ("dblp", False, "DBLP 计算机科学索引"),
        ("core", True, "CORE 全文开放获取"),
        ("pubmed", False, "PubMed 生物医学"),
    ],
    "patent": [
        ("epo_ops", True, "EPO OPS 欧洲专利 (OAuth)"),
        ("uspto_odp", True, "USPTO ODP 官方 API"),
        ("the_lens", True, "The Lens 全球专利+论文"),
        ("cnipa", True, "CNIPA 中国知识产权局 (OAuth)"),
        ("patsnap", True, "PatSnap 智慧芽"),
        ("google_patents", False, "Google Patents 实验性爬虫"),
    ],
    "general": [
        ("duckduckgo", False, "DuckDuckGo (爬虫)"),
        ("yahoo", False, "Yahoo (爬虫)"),
        ("brave", False, "Brave (爬虫，易限流)"),
        ("google", False, "Google (爬虫, 高风险)"),
        ("bing", False, "Bing (爬虫)"),
        ("startpage", False, "Startpage 隐私搜索 (爬虫)"),
        ("baidu", False, "百度搜索 (爬虫)"),
        ("mojeek", False, "Mojeek 独立搜索 (爬虫)"),
        ("yandex", False, "Yandex 搜索 (爬虫)"),
        ("searxng", True, "SearXNG 元搜索 (需自建实例)"),
        ("whoogle", True, "Whoogle Google 代理 (需自建实例)"),
        ("websurfx", True, "Websurfx 元搜索 (需自建实例)"),
        ("serpapi", True, "SerpAPI 多引擎 SERP"),
        ("brave_api", True, "Brave 官方 API"),
        ("serper", True, "Serper Google SERP API"),
        ("scrapingdog", True, "ScrapingDog SERP API"),
    ],
    "professional": [
        ("tavily", True, "Tavily AI 搜索"),
        ("exa", True, "Exa 语义搜索"),
        ("perplexity", True, "Perplexity Sonar AI 搜索"),
        ("firecrawl", True, "Firecrawl 搜索+爬取"),
        ("linkup", True, "Linkup 实时搜索"),
    ],
    "social": [
        ("reddit", False, "Reddit 帖子搜索"),
        ("weibo", False, "微博搜索 (爬虫)"),
        ("zhihu", False, "知乎问答搜索 (爬虫)"),
    ],
    "developer": [
        ("github", False, "GitHub 仓库搜索 (可选 Token)"),
        ("stackoverflow", False, "StackOverflow 问答搜索 (可选 Key)"),
    ],
    "wiki": [
        ("wikipedia", False, "Wikipedia 百科搜索"),
    ],
    "video": [
        ("youtube", False, "YouTube 视频搜索 (可选 Key)"),
        ("bilibili", False, "Bilibili 视频搜索 (爬虫)"),
    ],
    "fetch": [
        ("jina_reader", False, "Jina Reader 内容抓取 (免费)"),
        ("tavily", True, "Tavily Extract 内容抓取"),
        ("firecrawl", True, "Firecrawl Scrape 内容抓取"),
        ("exa", True, "Exa Contents 内容抓取"),
    ],
}
