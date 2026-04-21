"""Bilibili 全功能集成包

提供 B 站 Web API 的精简客户端，聚焦 SouWen 的核心使命：搜索 + 抓取。

公开能力：
- 视频搜索（含 WBI 签名）
- 用户搜索
- 专栏文章搜索
- 视频详情抓取（按 BV 号）

公开接口：
    BilibiliClient  — 主客户端类（继承 BaseScraper）
"""

from souwen.web.bilibili.client import BilibiliClient
from souwen.web.bilibili.models import (
    BilibiliArticleResult,
    BilibiliSearchUserItem,
    BilibiliVideoDetail,
    VideoOwner,
    VideoStat,
)

__all__ = [
    "BilibiliClient",
    "BilibiliArticleResult",
    "BilibiliSearchUserItem",
    "BilibiliVideoDetail",
    "VideoOwner",
    "VideoStat",
]
