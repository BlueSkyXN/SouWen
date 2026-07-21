"""SouWen 统一数据模型（Pydantic v2）

文件用途：
    定义所有数据源返回结果的统一 Pydantic 数据模型，确保 AI Agent 获得一致的数据结构。
    支持论文、专利、网页三大类结果以及统一的 SearchResponse 容器，
    所有模型采用 ConfigDict(extra="allow") 兼容上游字段扩展。

类清单（[已修正] 与实际定义对齐）：
    Author（BaseModel）
        - 功能：论文作者
        - 字段：name (必填), affiliation, orcid

    PaperResult（BaseModel）
        - 功能：单篇论文的统一模型
        - 关键字段：source (registry adapter name), title, authors (list[Author]), abstract,
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
        - 字段：title (必填), url (必填), snippet, source (registry adapter name), engine,
                rank (排序位次), published_date, raw

    SearchResponse（BaseModel）
        - 功能：单一数据源的搜索响应容器
        - 字段：source (registry adapter name), query, total_count, results (list[Any]),
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
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
        source: registry adapter name
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
    source: str
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


ResourceAccessStatus = Literal[
    "metadata_only",
    "preview",
    "borrow",
    "open_access",
    "public_domain",
    "restricted",
    "unknown",
]


class BookIdentifier(BaseModel):
    """A typed bibliographic identifier; schemes are never collapsed into one string."""

    model_config = ConfigDict(extra="forbid")

    scheme: Literal["isbn10", "isbn13", "lccn", "oclc", "olid", "doi", "source_record_id"]
    value: str

    @field_validator("value")
    @classmethod
    def _validate_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("book identifier value 不能为空")
        return normalized


class ResourceAccess(BaseModel):
    """Explicit access semantics for a catalog resource, without inferring download rights."""

    model_config = ConfigDict(extra="forbid")

    status: ResourceAccessStatus = "unknown"
    rights: str | None = None
    license_url: str | None = None
    region: str | None = None
    notes: str | None = None
    machine_download: bool | None = None


class ResourceLink(BaseModel):
    """A source-provided resource link, such as a cover or external catalog record."""

    model_config = ConfigDict(extra="forbid")

    url: str
    relation: str
    label: str | None = None
    file_name: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    media_type: str | None = None
    format: str | None = None
    source: str
    access: ResourceAccess = Field(default_factory=ResourceAccess)


class BookEdition(BaseModel):
    """Bounded edition metadata attached to a work-level book record."""

    model_config = ConfigDict(extra="forbid")

    olid: str | None = None
    publishers: list[str] = Field(default_factory=list)
    publication_date: str | None = None
    formats: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    page_count: int | None = None
    identifiers: list[BookIdentifier] = Field(default_factory=list)
    resources: list[ResourceLink] = Field(default_factory=list)


class BookAudioSection(BaseModel):
    """One bounded audiobook section with its upstream reader and audio-link metadata."""

    model_config = ConfigDict(extra="forbid")

    source_section_id: str
    section_number: int | None = None
    title: str | None = None
    readers: list[Author] = Field(default_factory=list)
    duration_seconds: int | None = Field(default=None, ge=0)
    resource: ResourceLink | None = None


class BookResult(BaseModel):
    """A work-level normalized book catalog record with explicit provenance and access state."""

    model_config = ConfigDict(extra="forbid")

    source: str
    source_record_id: str
    title: str
    authors: list[Author] = Field(default_factory=list)
    contributors: list[Author] = Field(default_factory=list)
    readers: list[Author] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)
    funding: list[str] = Field(default_factory=list)
    first_publish_year: int | None = None
    copyright_year: int | None = None
    description: str | None = None
    identifiers: list[BookIdentifier] = Field(default_factory=list)
    editions: list[BookEdition] = Field(default_factory=list)
    audio_sections: list[BookAudioSection] = Field(default_factory=list)
    resources: list[ResourceLink] = Field(default_factory=list)
    access: ResourceAccess = Field(default_factory=lambda: ResourceAccess(status="metadata_only"))
    source_url: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WikisourceSection(BaseModel):
    """A heading derived from a bounded Wikisource page revision."""

    model_config = ConfigDict(extra="forbid")

    title: str
    level: int = Field(ge=1, le=6)
    start_offset: int = Field(ge=0)


class WikisourceRevision(BaseModel):
    """One explicitly requested Wikisource revision and its bounded content."""

    model_config = ConfigDict(extra="forbid")

    revision_id: int
    parent_revision_id: int | None = None
    timestamp: datetime
    user: str | None = None
    comment: str | None = None
    content_model: str | None = None
    sha1: str | None = None
    content: str
    content_format: Literal["wikitext", "text", "html"]
    content_size_bytes: int | None = Field(default=None, ge=0)
    content_truncated: bool = False
    content_omitted_due_to_size: bool = False
    next_start_offset: int | None = Field(default=None, ge=0)


class WikisourcePageReference(BaseModel):
    """A bounded page reference, used for Wikisource subpage relations."""

    model_config = ConfigDict(extra="forbid")

    page_id: int
    title: str
    source_url: str


class WikisourcePage(BaseModel):
    """A language-bound Wikisource page with revision and rights provenance."""

    model_config = ConfigDict(extra="forbid")

    source: str = "wikisource"
    language: str
    site_url: str
    page_id: int
    title: str
    canonical_title: str
    source_url: str
    revision: WikisourceRevision
    redirected_from: str | None = None
    sections: list[WikisourceSection] = Field(default_factory=list)
    parent_title: str | None = None
    subpages: list[WikisourcePageReference] = Field(default_factory=list)
    site_content_access: ResourceAccess
    source_work_access: ResourceAccess
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CitationIdentifier(BaseModel):
    """A typed persistent identifier carried by an OpenCitations relation.

    The model deliberately permits identifier schemes beyond the three request
    schemes accepted by the OpenCitations client.  Citation-edge payloads can
    legitimately carry related ``openalex`` or other upstream identifiers and
    must not lose that provenance while normalizing a requested DOI/PMID/OMID.
    """

    model_config = ConfigDict(extra="forbid")

    scheme: str
    value: str

    @field_validator("scheme")
    @classmethod
    def _normalize_scheme(cls, value: str) -> str:
        value = value.strip().lower()
        if not value or not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("citation identifier scheme 非法")
        return value

    @field_validator("value")
    @classmethod
    def _normalize_value(cls, value: str) -> str:
        value = value.strip()
        if not value or any(char.isspace() for char in value):
            raise ValueError("citation identifier value 非法")
        return value

    @property
    def canonical(self) -> str:
        """Canonical upstream ``scheme:value`` rendering."""
        return f"{self.scheme}:{self.value}"


class CitationEdge(BaseModel):
    """One directed OpenCitations edge with source identifiers and provenance."""

    model_config = ConfigDict(extra="forbid")

    oci: str
    citing: list[CitationIdentifier] = Field(default_factory=list)
    cited: list[CitationIdentifier] = Field(default_factory=list)
    citing_raw: str
    cited_raw: str
    creation: str | None = None
    timespan: str | None = None
    journal_self_citation: bool | None = None
    author_self_citation: bool | None = None
    source: str = "opencitations"
    raw: dict = Field(default_factory=dict)


class CitationCountResponse(BaseModel):
    """Citation-count enrichment result for one identifier."""

    model_config = ConfigDict(extra="forbid")

    identifier: CitationIdentifier
    source: str = "opencitations"
    count: int = Field(ge=0)
    source_url: str
    rights: str = "CC0-1.0"
    license_url: str = "https://creativecommons.org/public-domain/cc0/"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CitationGraphResponse(BaseModel):
    """Incoming-citation or reference enrichment result for one identifier."""

    model_config = ConfigDict(extra="forbid")

    identifier: CitationIdentifier
    relation: Literal["citations", "references"]
    source: str = "opencitations"
    total_edges: int = Field(ge=0)
    returned_edges: int = Field(ge=0)
    truncated: bool = False
    edges: list[CitationEdge] = Field(default_factory=list)
    source_url: str
    rights: str = "CC0-1.0"
    license_url: str = "https://creativecommons.org/public-domain/cc0/"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
        source: registry adapter name
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
    source: str
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

    source: str
    title: str
    url: str
    snippet: str = ""
    engine: str  # 引擎标识: duckduckgo / yahoo / brave
    raw: dict = Field(default_factory=dict)


# ── Enriched web search contracts ───────────────────────────


def _require_http_url(value: str, *, field_name: str) -> str:
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field_name} 必须是带 hostname 的 http/https URL")
    return value


class SearchSnippet(BaseModel):
    """A result text fragment with an explicit origin instead of an ambiguous summary."""

    model_config = ConfigDict(extra="forbid")

    text: str
    type: Literal["provider_snippet", "provider_summary", "extractive", "generated"]
    provider: str | None = None
    model: str | None = None

    @field_validator("text")
    @classmethod
    def _require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text 不能为空")
        return value


class SearchSourceProvenance(BaseModel):
    """Auditable identity for one source attempt that discovered a candidate."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    scheme_id: str
    gateway_id: str | None = None
    upstream_channel: str | None = None
    requested_model_id: str | None = None
    served_model_id: str | None = None
    protocol: str | None = None
    tool_schema: str | None = None
    search_call_status: str | None = None
    response_status: str | None = None
    partial: bool = False
    incomplete_reason: str | None = None
    attempt_index: int = Field(default=1, ge=1)
    source_strategy: Literal["single", "fanout", "first_success"] = "single"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("source_id", "scheme_id")
    @classmethod
    def _require_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source/scheme/model identity 不能为空")
        return value


class SearchCandidate(BaseModel):
    """Internal discovery state; title may be absent until the fetch title gate succeeds."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    url: str
    provider_snippet: SearchSnippet | None = None
    published_at: str | None = None
    site_name: str | None = None
    favicon_url: str | None = None
    provenance: SearchSourceProvenance

    @field_validator("url", "favicon_url")
    @classmethod
    def _validate_urls(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _require_http_url(value, field_name=info.field_name)

    @field_validator("title")
    @classmethod
    def _normalize_optional_title(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class EnrichedWebSearchResult(BaseModel):
    """Final enriched result; title, URL and discovery provenance are mandatory."""

    model_config = ConfigDict(extra="forbid")

    result_id: str
    rank: int = Field(ge=1)
    title: str
    url: str
    canonical_url: str
    provider_snippet: SearchSnippet | None = None
    content_excerpt: SearchSnippet | None = None
    content: str | None = None
    summary: SearchSnippet | None = None
    published_at: str | None = None
    site_name: str | None = None
    site_domain: str
    favicon_url: str | None = None
    discoveries: list[SearchSourceProvenance] = Field(min_length=1)
    fetch_status: Literal["not_requested", "success", "failed"]
    fetch_provider: str | None = None
    fetch_error: str | None = None
    content_hash: str | None = None

    @field_validator("result_id", "title", "site_domain")
    @classmethod
    def _require_nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required result field 不能为空")
        return value

    @field_validator("url", "canonical_url", "favicon_url")
    @classmethod
    def _validate_result_urls(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _require_http_url(value, field_name=info.field_name)

    @model_validator(mode="after")
    def _validate_snippet_origins(self) -> "EnrichedWebSearchResult":
        if self.content_excerpt is not None and self.content_excerpt.type != "extractive":
            raise ValueError("content_excerpt 必须是 extractive snippet")
        if self.summary is not None and self.summary.type != "generated":
            raise ValueError("summary 必须是 generated snippet")
        return self


class SearchResponse(BaseModel):
    """统一搜索响应"""

    model_config = ConfigDict(extra="forbid")
    query: str
    source: str
    total_results: int | None = None
    results: list[PaperResult] | list[PatentResult] | list[BookResult] | list[WebSearchResult]
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
    content_truncated: bool = False  # 内容是否因 max_length 被截断
    next_start_index: int | None = None  # 续读起点（仅在截断时设置）
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
    providers: list[str] = Field(default_factory=list)
    strategy: str = "fallback"
    provider: str | None = Field(
        default=None,
        description=(
            "Deprecated single-provider summary field. Use providers plus "
            "meta.selected_provider for per-URL attribution."
        ),
        json_schema_extra={
            "deprecated": True,
            "x-souwen-sunset": "2.1.0 GA",
        },
    )
    meta: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize_provider_fields(self) -> "FetchResponse":
        """Keep deprecated ``provider`` and canonical ``providers`` compatible."""
        if not self.providers and self.provider:
            self.providers = [self.provider]
        elif self.provider is None and len(self.providers) == 1:
            self.provider = self.providers[0]
        return self


class WaybackSnapshot(BaseModel):
    """Wayback Machine 单个历史快照记录（CDX 格式）"""

    model_config = ConfigDict(extra="allow")
    timestamp: str  # YYYYMMDDHHMMSS 格式
    url: str  # 原始 URL
    archive_url: str  # 快照 URL（web.archive.org/web/...）
    status_code: int = 200  # HTTP 状态码
    mime_type: str = ""  # MIME 类型
    digest: str = ""  # 内容摘要（SHA-1）
    length: int = 0  # 内容长度（字节）
    published_date: str | None = None  # 格式化后的日期 YYYY-MM-DD


class WaybackCDXResponse(BaseModel):
    """Wayback Machine CDX Server API 响应"""

    model_config = ConfigDict(extra="allow")
    url: str  # 查询的 URL
    snapshots: list[WaybackSnapshot] = Field(default_factory=list)
    total: int = 0  # 快照总数
    from_date: str | None = None  # 查询起始日期（YYYYMMDD）
    to_date: str | None = None  # 查询结束日期（YYYYMMDD）
    filter_status: list[int] | None = None  # 过滤的状态码
    filter_mime: str | None = None  # 过滤的 MIME 类型
    error: str | None = None


class WaybackAvailability(BaseModel):
    """Wayback Machine Availability API 响应（archive.org/wayback/available）"""

    model_config = ConfigDict(extra="allow")
    url: str  # 查询的目标 URL
    available: bool = False  # 是否有可用存档
    snapshot_url: str | None = None  # 最近快照 URL（web.archive.org/web/...）
    timestamp: str | None = None  # 快照时间戳（YYYYMMDDHHMMSS）
    published_date: str | None = None  # 格式化日期（YYYY-MM-DD）
    status_code: int | None = None  # 快照原始 HTTP 状态码
    error: str | None = None


class WaybackSaveResult(BaseModel):
    """Wayback Machine Save Page Now 触发存档结果"""

    model_config = ConfigDict(extra="allow")
    url: str  # 请求保存的目标 URL
    success: bool = False  # 是否成功触发存档
    snapshot_url: str | None = None  # 存档后的快照 URL
    timestamp: str | None = None  # 快照时间戳（YYYYMMDDHHMMSS）
    error: str | None = None
