"""Bilibili 数据模型

所有 Bilibili API 返回结果的 Pydantic v2 数据模型。
这些模型仅用于 Bilibili 特有的详情接口（视频详情、用户信息、评论等），
聚合搜索仍使用主 models.py 中的 WebSearchResult。

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


# ── 用户信息 ─────────────────────────────────────────────


class UserVip(BaseModel):
    """用户大会员信息"""

    model_config = ConfigDict(extra="allow")
    vip_type: int = 0  # 0=无, 1=月度, 2=年度
    vip_status: int = 0  # 1=有效


class UserOfficial(BaseModel):
    """用户认证信息"""

    model_config = ConfigDict(extra="allow")
    role: int = 0
    title: str = ""
    desc: str = ""


class BilibiliUserInfo(BaseModel):
    """用户信息（/x/space/wbi/acc/info + /x/relation/stat 合并）"""

    model_config = ConfigDict(extra="allow")
    mid: int = 0
    name: str = ""
    face: str = ""  # 头像 URL
    sign: str = ""  # 签名
    level: int = 0
    sex: str = ""
    birthday: str = ""
    coins: float = 0.0
    following: int = 0  # 关注数（from /x/relation/stat）
    follower: int = 0  # 粉丝数（from /x/relation/stat）
    archive_count: int = 0  # 投稿数
    vip: UserVip = Field(default_factory=UserVip)
    official: UserOfficial = Field(default_factory=UserOfficial)
    live_room_url: str = ""
    live_status: int = 0  # 0=未开播, 1=直播中

    @property
    def space_url(self) -> str:
        return f"https://space.bilibili.com/{self.mid}" if self.mid else ""


# ── 评论 ──────────────────────────────────────────────────


class CommentMember(BaseModel):
    """评论者信息"""

    model_config = ConfigDict(extra="allow")
    mid: int = 0
    uname: str = ""
    avatar: str = ""
    level_info: dict = Field(default_factory=dict)


class CommentContent(BaseModel):
    """评论内容"""

    model_config = ConfigDict(extra="allow")
    message: str = ""


class BilibiliComment(BaseModel):
    """单条评论（/x/v2/reply）"""

    model_config = ConfigDict(extra="allow")
    rpid: int = 0  # 评论 ID
    mid: int = 0  # 发布者 UID
    ctime: int = 0  # 发布时间（Unix）
    like: int = 0  # 点赞数
    rcount: int = 0  # 回复数
    member: CommentMember = Field(default_factory=CommentMember)
    content: CommentContent = Field(default_factory=CommentContent)

    @property
    def text(self) -> str:
        return self.content.message


# ── 字幕 ──────────────────────────────────────────────────


class BilibiliSubtitleLine(BaseModel):
    """单行字幕"""

    model_config = ConfigDict(extra="allow")
    from_time: float = Field(0.0, alias="from")
    to_time: float = Field(0.0, alias="to")
    content: str = ""
    location: int = 0  # 0=无, 2=下方


class BilibiliSubtitle(BaseModel):
    """字幕信息"""

    model_config = ConfigDict(extra="allow")
    lan: str = ""  # 语言代码 (zh-CN, en 等)
    lan_doc: str = ""  # 语言名称
    subtitle_url: str = ""  # 字幕 JSON URL
    lines: list[BilibiliSubtitleLine] = Field(default_factory=list)

    @property
    def full_text(self) -> str:
        """将所有字幕行拼接为纯文本"""
        return "\n".join(line.content for line in self.lines if line.content)


# ── AI 摘要 ───────────────────────────────────────────────


class BilibiliAISummary(BaseModel):
    """视频 AI 摘要（/x/web-interface/view/conclusion/get）"""

    model_config = ConfigDict(extra="allow")
    summary: str = ""
    stids: list[int] = Field(default_factory=list)
    result_type: int = 0  # 0=无摘要, 其他=有


# ── 热门/排行 ─────────────────────────────────────────────


class BilibiliPopularVideo(BaseModel):
    """热门视频条目（/x/web-interface/popular）"""

    model_config = ConfigDict(extra="allow")
    bvid: str = ""
    aid: int = 0
    title: str = ""
    pic: str = ""
    description: str = Field("", alias="desc")
    duration: int = 0
    pubdate: int = 0
    owner: VideoOwner = Field(default_factory=VideoOwner)
    stat: VideoStat = Field(default_factory=VideoStat)
    rcmd_reason: str = ""  # 推荐理由

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}" if self.bvid else ""


class BilibiliRankVideo(BaseModel):
    """排行榜视频条目（/x/web-interface/ranking/v2）"""

    model_config = ConfigDict(extra="allow")
    bvid: str = ""
    aid: int = 0
    title: str = ""
    pic: str = ""
    description: str = Field("", alias="desc")
    duration: int = 0
    pubdate: int = 0
    owner: VideoOwner = Field(default_factory=VideoOwner)
    stat: VideoStat = Field(default_factory=VideoStat)
    rank_index: int = 0  # 排名位次
    score: int = 0  # 综合得分

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}" if self.bvid else ""


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


# ── 用户视频列表 ──────────────────────────────────────────


class BilibiliUserVideoItem(BaseModel):
    """用户视频列表条目（/x/space/wbi/arc/search）"""

    model_config = ConfigDict(extra="allow")
    bvid: str = ""
    aid: int = 0
    title: str = ""
    description: str = ""
    pic: str = ""  # 封面 URL
    length: str = ""  # "mm:ss" 格式时长
    play: int = 0  # 播放量
    comment: int = 0  # 评论数
    created: int = 0  # 发布时间（Unix）

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}" if self.bvid else ""


# ── 相关推荐 ──────────────────────────────────────────────


class BilibiliRelatedVideo(BaseModel):
    """相关推荐视频"""

    model_config = ConfigDict(extra="allow")
    bvid: str = ""
    aid: int = 0
    title: str = ""
    pic: str = ""
    duration: int = 0
    pubdate: int = 0
    owner: VideoOwner = Field(default_factory=VideoOwner)
    stat: VideoStat = Field(default_factory=VideoStat)

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}" if self.bvid else ""
