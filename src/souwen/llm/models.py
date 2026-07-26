"""SouWen LLM 数据模型

LLM 集成相关的请求/响应数据模型。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMMessage(BaseModel):
    """LLM 对话消息"""

    role: Literal["system", "user", "assistant"] = "user"
    content: str


class LLMUsage(BaseModel):
    """LLM token 用量统计"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """LLM 完成响应"""

    content: str  # 生成的文本
    model: str = ""  # 实际使用的模型名
    usage: LLMUsage = Field(default_factory=LLMUsage)
    finish_reason: str = ""  # stop / length / content_filter


class EnrichedSynthesisAnswer(BaseModel):
    """A citation-bounded answer generated from enriched-search material."""

    model_config = ConfigDict(extra="forbid")

    text: str
    citations: list[str] = Field(min_length=1)
    profile: str
    model: str
    protocol: Literal["openai_chat", "openai_responses", "anthropic_messages"]


class SummaryCitation(BaseModel):
    """摘要中的引用"""

    id: int  # [1], [2], ... 引用编号
    title: str = ""
    url: str = ""
    source: str = ""  # 数据源标识 (openalex, duckduckgo, etc.)


class DeepFetchStats(BaseModel):
    """Deep Search 的内容抓取统计"""

    fetched_urls: list[str] = Field(default_factory=list)
    failed_urls: list[str] = Field(default_factory=list)
    used_urls: list[str] = Field(default_factory=list)  # actually used in synthesis
    skipped_urls: list[str] = Field(default_factory=list)  # fetched but dropped (empty/short)


class DeepSummaryResult(BaseModel):
    """Deep Search 深度搜索综合摘要"""

    model_config = ConfigDict(extra="forbid")

    query: str
    summary: str  # 基于全文内容的深度综合
    mode: Literal["brief", "detailed", "academic"] = "brief"
    citations: list[SummaryCitation] = Field(default_factory=list)
    model: str = ""
    usage: LLMUsage = Field(default_factory=LLMUsage)
    fetch_stats: DeepFetchStats = Field(default_factory=DeepFetchStats)
    sources_used: int = 0
    results_used: int = 0
    pages_synthesized: int = 0  # number of pages actually used in synthesis
