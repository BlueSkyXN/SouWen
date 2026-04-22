"""SouWen 核心平台层

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
  - models         —— 数据模型（位于 souwen.models）

`souwen` 根目录下的同名模块（如 `souwen.http_client`）作为公开入口 re-export 自本包，
两条路径等价；新代码推荐 `from souwen.core.xxx import ...`。
"""

from __future__ import annotations

from souwen.core.concurrency import (
    clear_semaphore,
    get_max_concurrency,
    get_semaphore,
)

__all__ = ["get_semaphore", "get_max_concurrency", "clear_semaphore"]
