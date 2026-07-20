"""Bilibili 直连 REST 响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _BilibiliExtraModel(BaseModel):
    """Bilibili 上游字段变化较频繁，REST 响应保留兼容扩展字段。"""

    model_config = ConfigDict(extra="allow")


class BilibiliSearchItemResponse(_BilibiliExtraModel):
    """Bilibili 视频搜索结果条目。"""

    bvid: str = ""
    aid: int | None = None
    title: str = ""
    author: str = ""
    mid: int | None = None
    play: int = 0
    danmaku: int = 0
    favorites: int | None = None
    description: str = ""
    duration: str = ""
    pic: str = ""
    pubdate: int | None = None
    tag: str | None = None
    type: str | None = "video"
    url: str = ""


class BilibiliSearchResponse(BaseModel):
    """``GET /bilibili/search`` 响应。"""

    keyword: str
    results: list[BilibiliSearchItemResponse] = Field(default_factory=list)
    total: int
    page: int = 1
    page_size: int | None = None
    order: str | None = None


class BilibiliVideoOwnerResponse(_BilibiliExtraModel):
    """Bilibili 视频 UP 主信息。"""

    mid: int = 0
    name: str = ""
    face: str = ""


class BilibiliVideoStatResponse(_BilibiliExtraModel):
    """Bilibili 视频统计信息。"""

    view: int = 0
    danmaku: int = 0
    reply: int = 0
    favorite: int = 0
    coin: int = 0
    share: int = 0
    like: int = 0


class BilibiliVideoDetailDataResponse(_BilibiliExtraModel):
    """Bilibili 视频详情数据。"""

    bvid: str = ""
    aid: int = 0
    cid: int = 0
    title: str = ""
    description: str = ""
    pic: str = ""
    duration: int = 0
    pubdate: int = 0
    ctime: int = 0
    owner: BilibiliVideoOwnerResponse = Field(default_factory=BilibiliVideoOwnerResponse)
    stat: BilibiliVideoStatResponse = Field(default_factory=BilibiliVideoStatResponse)
    tname: str = ""
    dynamic: str = ""
    tags: list[str] = Field(default_factory=list)


class BilibiliVideoDetailResponse(BaseModel):
    """``GET /bilibili/video/{bvid}`` 响应。"""

    bvid: str
    data: BilibiliVideoDetailDataResponse


class BilibiliUserItemResponse(_BilibiliExtraModel):
    """Bilibili 用户搜索结果条目。"""

    mid: int = 0
    uname: str = ""
    usign: str = ""
    fans: int = 0
    videos: int = 0
    level: int = 0
    upic: str = ""
    official_verify_type: int = -1


class BilibiliUserSearchResponse(BaseModel):
    """``GET /bilibili/search/users`` 响应。"""

    keyword: str
    results: list[BilibiliUserItemResponse] = Field(default_factory=list)
    total: int
    page: int = 1


class BilibiliArticleItemResponse(_BilibiliExtraModel):
    """Bilibili 专栏文章搜索结果条目。"""

    id: int = 0
    title: str = ""
    author: str = ""
    mid: int = 0
    category_name: str = ""
    desc: str = ""
    description: str = ""
    view: int = 0
    like: int = 0
    reply: int = 0
    pub_date: int = 0
    url: str = ""
    image_urls: list[str] = Field(default_factory=list)


class BilibiliArticleSearchResponse(BaseModel):
    """``GET /bilibili/search/articles`` 响应。"""

    keyword: str
    results: list[BilibiliArticleItemResponse] = Field(default_factory=list)
    total: int
    page: int = 1
