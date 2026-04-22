"""video/ — 视频平台搜索域

Public API: re-export 视频客户端，保持对外 import 稳定。

Sources: youtube / bilibili
"""

from souwen.web.bilibili import BilibiliClient
from souwen.web.youtube import YouTubeClient

__all__ = ["YouTubeClient", "BilibiliClient"]
