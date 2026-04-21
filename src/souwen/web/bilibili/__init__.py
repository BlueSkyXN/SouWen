"""Bilibili 全功能集成包

提供 B 站 Web API 的完整 Python 客户端，包括：
- 视频搜索（含 WBI 签名）
- 视频详情、评论、字幕、AI 摘要
- 用户信息、用户视频列表
- 热门视频、排行榜
- 相关推荐

公开接口：
    BilibiliClient  — 主客户端类（继承 BaseScraper）
"""

from souwen.web.bilibili.client import BilibiliClient

__all__ = ["BilibiliClient"]
