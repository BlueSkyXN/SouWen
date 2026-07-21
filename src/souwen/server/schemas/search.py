"""搜索响应模型 — 论文 / 专利 / 网页 / 图片 / 视频"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from souwen.models import EnrichedWebSearchResult, SearchResponse
from souwen.server.schemas.common import SearchMeta


class SearchPaperResponse(BaseModel):
    """论文搜索响应"""

    query: str
    sources: list[str]
    results: list[dict]
    total: int
    meta: SearchMeta = Field(
        default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[])
    )


class SearchBookResponse(BaseModel):
    """Book search response with work-level records from registry-backed sources."""

    query: str
    sources: list[str]
    results: list[dict]
    total: int
    meta: SearchMeta = Field(
        default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[])
    )


class SearchResearchOutputResponse(BaseModel):
    """Research-output search response preserving typed per-source result envelopes."""

    query: str
    sources: list[str]
    results: list[SearchResponse]
    total: int
    meta: SearchMeta = Field(
        default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[])
    )


class SearchPatentResponse(BaseModel):
    """专利搜索响应

    结构与 SearchPaperResponse 相同，sources 替换为专利数据源。
    """

    query: str
    sources: list[str]
    results: list[dict]
    total: int
    meta: SearchMeta = Field(
        default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[])
    )


class SearchWebResponse(BaseModel):
    """/search/web 响应 — 对齐 paper/patent 的统一结构"""

    query: str
    engines: list[str]
    results: list[dict]
    total: int
    meta: SearchMeta = Field(
        default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[])
    )


class SearchImagesResponse(BaseModel):
    """图片搜索响应 — DuckDuckGo Images"""

    query: str
    results: list[dict]
    total: int
    meta: SearchMeta = Field(
        default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[])
    )


class SearchVideosResponse(BaseModel):
    """视频搜索响应 — DuckDuckGo Videos"""

    query: str
    results: list[dict]
    total: int
    meta: SearchMeta = Field(
        default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[])
    )


class EnrichedSearchFetchRequest(BaseModel):
    """Bounded fetch options for ``POST /search/web/enriched``."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(True, description="是否在搜索后抓取页面正文")
    providers: list[str] | None = Field(
        None,
        min_length=1,
        max_length=10,
        description="可选 fetch provider allowlist；为空时使用现有 fetch 默认策略",
    )
    strategy: Literal["fallback", "fanout"] = Field(
        "fallback", description="fetch provider 调度策略"
    )
    max_pages: int = Field(5, ge=1, le=20, description="本次最多抓取的去重页面数")
    max_excerpt_chars: int = Field(500, ge=1, le=4_000, description="每条 extractive excerpt 上限")
    include_content: bool = Field(False, description="是否返回受限的真实页面正文")
    max_content_chars: int = Field(4_000, ge=1, le=20_000, description="每条返回正文的最大字符数")

    @field_validator("providers", mode="before")
    @classmethod
    def _normalize_providers(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, list | tuple):
            return value
        return [item.strip() if isinstance(item, str) else item for item in value]

    @field_validator("providers")
    @classmethod
    def _require_nonempty_providers(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and any(not provider for provider in value):
            raise ValueError("providers 不能包含空字符串")
        return value


class EnrichedSearchBudgetRequest(BaseModel):
    """Endpoint-wide and source-attempt bounds for enriched search."""

    model_config = ConfigDict(extra="forbid")

    max_total_seconds: float = Field(
        120.0, ge=1.0, le=300.0, description="搜索与抓取共享的端点硬超时（秒）"
    )
    max_source_attempts: int = Field(
        1, ge=1, le=10, description="最多执行的 concrete source attempt 数"
    )


class EnrichedSearchSynthesisRequest(BaseModel):
    """A request may select only a deployment-owned synthesis profile."""

    model_config = ConfigDict(extra="forbid")

    profile: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="部署配置 allowlist 中的 synthesis profile ID",
    )

    @field_validator("profile", mode="before")
    @classmethod
    def _normalize_profile(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class EnrichedWebSearchRequest(BaseModel):
    """Additive, model-bound request contract for enriched web search."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=500, description="搜索关键词")
    sources: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="已注册的 concrete LLM-search source IDs；不接受 scheme 或 model ID",
    )
    source_strategy: Literal["single", "fanout", "first_success"] = Field(
        "single", description="single 必须恰好一个 source；其他策略必须显式指定"
    )
    max_results_per_source: int = Field(10, ge=1, le=50, description="每个 source 的结果上限")
    deduplicate: bool = Field(True, description="是否按 canonical URL 合并发现记录")
    fetch: EnrichedSearchFetchRequest = Field(default_factory=EnrichedSearchFetchRequest)
    budget: EnrichedSearchBudgetRequest = Field(default_factory=EnrichedSearchBudgetRequest)
    synthesis: EnrichedSearchSynthesisRequest | None = Field(
        None,
        description="可选的服务端 synthesis；只能选择配置 allowlist profile，不能指定 model",
    )

    @field_validator("query", mode="before")
    @classmethod
    def _normalize_query(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("sources", mode="before")
    @classmethod
    def _normalize_sources(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        return [item.strip() if isinstance(item, str) else item for item in value]

    @model_validator(mode="after")
    def _validate_strategy_budget(self) -> "EnrichedWebSearchRequest":
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("sources 不能包含重复 source ID")
        if self.source_strategy == "single" and len(self.sources) != 1:
            raise ValueError("source_strategy=single 时必须恰好选择一个 source")
        if self.source_strategy == "fanout" and self.budget.max_source_attempts < len(self.sources):
            raise ValueError("fanout 的 max_source_attempts 不得小于 sources 数量")
        return self


class EnrichedSearchSourceAttemptResponse(BaseModel):
    """Public, provider-raw-free record for one concrete source attempt."""

    source_id: str
    attempt_index: int = Field(ge=1)
    outcome: Literal["success_with_results", "success_empty", "timeout", "failed"]
    visible_search_calls: int | None = Field(
        None, ge=0, description="响应中可观测到的 search call 数；不是账单推断"
    )
    provider_metered_search_calls: int | None = Field(
        None, ge=0, description="仅在 provider 明确返回时提供；未知为 null"
    )


class EnrichedSearchMetaResponse(BaseModel):
    """Safe stage outcomes and source-attempt evidence."""

    requested_sources: list[str]
    source_strategy: Literal["single", "fanout", "first_success"]
    source_outcomes: dict[
        str, Literal["success_with_results", "success_empty", "timeout", "failed"]
    ]
    partial: bool
    discarded_candidates: int = Field(ge=0)
    source_attempts: list[EnrichedSearchSourceAttemptResponse]
    visible_search_calls: int = Field(ge=0)
    provider_metered_search_calls: int | None = Field(None, ge=0)
    fetched_pages: int = Field(ge=0)
    synthesis_status: Literal["not_requested", "success", "failed", "skipped"] = Field(
        "not_requested", description="optional synthesis stage outcome；失败不会丢弃搜索结果"
    )
    summarized_pages: int = Field(0, ge=0, description="成功生成的 result-level summary 数量")


class EnrichedSearchUsageResponse(BaseModel):
    """Usage fields retain unknown values as null instead of inventing a cost."""

    search_input_tokens: int | None = Field(None, ge=0)
    search_output_tokens: int | None = Field(None, ge=0)
    summary_input_tokens: int | None = Field(None, ge=0)
    summary_output_tokens: int | None = Field(None, ge=0)
    search_tool_cost: float | None = Field(None, ge=0)
    currency: str | None = None


class EnrichedSearchAnswerResponse(BaseModel):
    """Generated answer whose citations are validated result IDs, never URLs."""

    text: str
    citations: list[str]
    profile: str
    model: str
    protocol: Literal["openai_chat", "openai_responses", "anthropic_messages"]


class EnrichedWebSearchResponse(BaseModel):
    """Typed response for the additive enriched search route."""

    query: str
    results: list[EnrichedWebSearchResult]
    answer: EnrichedSearchAnswerResponse | None = None
    meta: EnrichedSearchMetaResponse
    usage: EnrichedSearchUsageResponse
