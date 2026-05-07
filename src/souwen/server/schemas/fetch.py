"""内容抓取请求模型"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from souwen.registry import fetch_providers

_FETCH_PROVIDER_NAMES = tuple(adapter.name for adapter in fetch_providers())


class FetchRequest(BaseModel):
    """内容抓取请求体

    Attributes:
        urls: 目标 URL 列表（1-20 条）
        provider: 兼容旧版单 provider 字段（默认 builtin）
        providers: 多 provider 列表；提供时优先于 provider
        strategy: 多 provider 策略，fallback 或 fanout
        timeout: 每个 URL 超时秒数
    """

    urls: list[str] = Field(..., min_length=1, max_length=20)
    provider: str = Field(
        default="builtin",
        description=f"兼容单抓取提供者，可选: {', '.join(_FETCH_PROVIDER_NAMES)}",
    )
    providers: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description=f"抓取提供者列表；提供时优先于 provider，可选: {', '.join(_FETCH_PROVIDER_NAMES)}",
    )
    strategy: Literal["fallback", "fanout"] = Field(
        default="fallback",
        description="多提供者策略：fallback 按 URL 补失败项，fanout 并发返回全部 provider 结果",
    )
    timeout: float = Field(default=30.0, ge=1.0, le=120.0)
    selector: str | None = Field(
        default=None,
        description="CSS 选择器，仅提取匹配元素（builtin / scrapling 提供者支持）",
    )
    start_index: int = Field(default=0, ge=0, description="内容起始切片位置（用于分页续读）")
    max_length: int | None = Field(default=None, ge=0, description="内容最大长度，超出则截断")
    respect_robots_txt: bool = Field(default=False, description="是否遵守 robots.txt")
