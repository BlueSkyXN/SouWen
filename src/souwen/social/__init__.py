"""social/ — 社交平台搜索域（v1）

re-export v0 的 social 客户端，保持对外 import 稳定。

Sources: reddit / twitter / facebook / weibo / zhihu
"""

from souwen.web.facebook import FacebookClient
from souwen.web.reddit import RedditClient
from souwen.web.twitter import TwitterClient
from souwen.web.weibo import WeiboClient
from souwen.web.zhihu import ZhihuClient

__all__ = [
    "RedditClient",
    "TwitterClient",
    "FacebookClient",
    "WeiboClient",
    "ZhihuClient",
]
