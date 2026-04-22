"""内容抓取请求模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FetchRequest(BaseModel):
    """内容抓取请求体

    Attributes:
        urls: 目标 URL 列表（1-20 条）
        provider: 提供者名称（默认 builtin）
        timeout: 每个 URL 超时秒数
    """

    urls: list[str] = Field(..., min_length=1, max_length=20)
    provider: str = Field(default="builtin")
    timeout: float = Field(default=30.0, ge=1.0, le=120.0)
    selector: str | None = Field(
        default=None,
        description="CSS 选择器，仅提取匹配元素（仅 builtin 提供者支持）",
    )
    start_index: int = Field(default=0, ge=0, description="内容起始切片位置（用于分页续读）")
    max_length: int | None = Field(default=None, ge=0, description="内容最大长度，超出则截断")
    respect_robots_txt: bool = Field(default=False, description="是否遵守 robots.txt")
