"""搜索响应模型 — 论文 / 专利 / 网页 / 图片 / 视频"""

from __future__ import annotations

from pydantic import BaseModel, Field

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
