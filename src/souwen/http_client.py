"""v1 shim: 请改用 `souwen.core.http_client`。

v0 历史位置保持可用：
    from souwen.http_client import SouWenHttpClient, OAuthClient, DEFAULT_USER_AGENT
内部实际指向 `souwen.core.http_client`（v1 真身）。
"""

from souwen.core.http_client import *  # noqa: F401,F403
from souwen.core.http_client import (  # noqa: F401
    DEFAULT_USER_AGENT,
    OAuthClient,
    SouWenHttpClient,
)
