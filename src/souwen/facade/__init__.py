"""facade/ — v1 门面层

门面层负责把请求分发到具体数据源客户端，做并发调度 / 超时保护 / 异常隔离。
具体客户端通过 `souwen.registry` 派发，不直接 import。

模块：
  - search     —— 按 domain 搜索（search(domain="paper", ...)）+ 各 domain 辅助函数
  - fetch      —— 内容抓取（fetch_content(urls, provider=...)）
  - archive    —— Wayback 归档查询（archive_lookup/save/fetch）
  - aggregate  —— 多 domain 并发聚合（search_all）

v0 兼容入口：
  - `souwen.search.search_papers()` / `search_patents()` / `web_search()`
  - `souwen.web.fetch.fetch_content()` / `souwen.web.wayback.WaybackClient`
    均可继续使用；facade 层是新入口，不破坏旧路径。
"""

from __future__ import annotations

from souwen.facade.aggregate import search_all
from souwen.facade.archive import (
    archive_check,
    archive_fetch,
    archive_lookup,
    archive_save,
)
from souwen.facade.fetch import fetch_content
from souwen.facade.search import (
    search,
    search_by_capability,
    search_domain,
    search_papers,
    search_patents,
)

__all__ = [
    # search
    "search",
    "search_domain",
    "search_by_capability",
    "search_papers",
    "search_patents",
    # fetch
    "fetch_content",
    # archive
    "archive_lookup",
    "archive_check",
    "archive_save",
    "archive_fetch",
    # aggregate
    "search_all",
]
