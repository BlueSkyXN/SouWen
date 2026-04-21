"""SouWen 核心平台层（v1 正式落地）

本包聚合所有"平台层"基础设施——与业务 domain 无关、被所有 Client 共用的底层组件。

模块：
  - http_client    —— SouWenHttpClient / OAuthClient
  - rate_limiter   —— Token Bucket + 滑窗限流
  - retry          —— 指数退避重试装饰器
  - session_cache  —— OAuth 令牌缓存
  - fingerprint    —— curl_cffi TLS 指纹
  - scraper        —— BaseScraper（给爬虫类客户端）
  - exceptions     —— 全部异常类型
  - parsing        —— 轻量 HTML/JSON 辅助解析
  - concurrency    —— per-loop Semaphore（D12）
  - models         —— （保留在 souwen.models，以兼容；未来版本迁到此处）

v0 兼容：所有 v0 根目录下的平台模块仍可直接 import（`from souwen.http_client import ...`），
它们现在都是本包的 re-export shim。新代码推荐 `from souwen.core.xxx import ...`。
"""

from __future__ import annotations

from souwen.core.concurrency import (
    clear_semaphore,
    get_max_concurrency,
    get_semaphore,
)

__all__ = ["get_semaphore", "get_max_concurrency", "clear_semaphore"]
