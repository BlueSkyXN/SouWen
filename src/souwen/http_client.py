"""Public re-export of `souwen.core.http_client`.

便捷入口：
    from souwen.http_client import SouWenHttpClient, OAuthClient, DEFAULT_USER_AGENT
"""

from souwen.core.http_client import *  # noqa: F401,F403
from souwen.core.http_client import (  # noqa: F401
    DEFAULT_USER_AGENT,
    OAuthClient,
    SouWenHttpClient,
)
