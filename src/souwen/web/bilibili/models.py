"""Bilibili 数据模型

仅保留 SouWen 核心使命（搜索 + 抓取）所需的数据模型：
    - 视频详情抓取（BilibiliVideoDetail）
    - 用户搜索结果（BilibiliSearchUserItem）
    - 文章/专栏搜索结果（BilibiliArticleResult）

聚合视频搜索仍使用主 models.py 中的 WebSearchResult；其他派生功能
（评论、字幕、AI 摘要、热门、排行、相关推荐、用户信息、用户视频列表）
属于 bili-cli 项目范畴，不在本仓库提供。

设计原则：
    - extra="allow" 兼容 Bilibili 接口字段变化
    - 所有字段带合理默认值，容忍上游缺字段
    - 统计数字统一为 int，缺失时默认 0
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# ── 视频详情 ─────────────────────────────────────────────


class VideoOwner(BaseModel):
    """视频 UP 主信息"""

    model_config = ConfigDict(extra="allow")
    mid: int = 0
    name: str = ""
    face: str = ""  # 头像 URL


class VideoStat(BaseModel):
    """视频统计数据"""

    model_config = ConfigDict(extra="allow")
    view: int = 0  # 播放
    danmaku: int = 0  # 弹幕
    reply: int = 0  # 评论
    favorite: int = 0  # 收藏
    coin: int = 0  # 投币
    share: int = 0  # 分享
    like: int = 0  # 点赞


class BilibiliVideoDetail(BaseModel):
    """视频详情（/x/web-interface/view）"""

    model_config = ConfigDict(extra="allow")
    bvid: str = ""
    aid: int = 0
    cid: int = 0  # 主分P的 cid
    title: str = ""
    description: str = ""
    pic: str = ""  # 封面图 URL
    duration: int = 0  # 总时长（秒）
    pubdate: int = 0  # 发布时间（Unix 时间戳）
    ctime: int = 0  # 创建时间
    owner: VideoOwner = Field(default_factory=VideoOwner)
    stat: VideoStat = Field(default_factory=VideoStat)
    tname: str = ""  # 分区名
    dynamic: str = ""  # 动态文字
    tags: list[str] = Field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}" if self.bvid else ""

    @property
    def duration_str(self) -> str:
        """时长格式化为 mm:ss"""
        m, s = divmod(self.duration, 60)
        return f"{m}:{s:02d}"


# ── 用户搜索结果 ──────────────────────────────────────────


class BilibiliSearchUserItem(BaseModel):
    """用户搜索结果条目"""

    model_config = ConfigDict(extra="allow")
    mid: int = 0
    uname: str = ""
    usign: str = ""  # 签名
    fans: int = 0  # 粉丝数
    videos: int = 0  # 视频数
    level: int = 0
    upic: str = ""  # 头像 URL
    official_verify_type: int = -1  # -1=无认证, 0=个人, 1=机构

    @property
    def space_url(self) -> str:
        return f"https://space.bilibili.com/{self.mid}" if self.mid else ""


# ── 专栏文章搜索结果 ───────────────────────────────────────


class BilibiliArticleResult(BaseModel):
    """B站专栏文章搜索结果（/x/web-interface/search/type?search_type=article）"""

    model_config = ConfigDict(extra="allow")

    id: int = 0
    title: str = ""
    author: str = ""
    mid: int = 0
    category_name: str = ""
    desc: str = ""
    view: int = 0
    like: int = 0
    reply: int = 0
    pub_date: int = 0
    url: str = ""
    image_urls: list[str] = Field(default_factory=list)
