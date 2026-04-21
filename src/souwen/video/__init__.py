"""video/ — 视频平台搜索域（v1）

re-export v0 的 video 客户端。

Sources: youtube / bilibili
"""

from souwen.web.bilibili import BilibiliClient
from souwen.web.youtube import YouTubeClient

__all__ = ["YouTubeClient", "BilibiliClient"]
