"""Google Patents 爬虫客户端（v1 统一实现）

v1 决定（参见 `local/v1-初步定义.md §2.2 / §9.1`）：

v0 时期此处有一份独立的 Playwright + 自写 _BrowserPool 实现，但 `search.py` 的
门面从未调用过它（实际走的是 `souwen.scraper.google_patents_scraper.GooglePatentsScraper`）。
它是孤儿代码，留着误导贡献者，且引入 playwright 依赖。v1 彻底删除。

为了保持 `from souwen.patent import GooglePatentsClient` 的 v0 兼容性：
`GooglePatentsClient` 名字继续可用，但指向 `scraper.GooglePatentsScraper`——
两者行为等价（都是同一个 HTML + XHR fallback 实现）。
"""

from __future__ import annotations

from souwen.scraper.google_patents_scraper import GooglePatentsScraper

#: v0 兼容别名：旧的 Playwright 版 GooglePatentsClient 已删除，
#: 用户 `from souwen.patent.google_patents import GooglePatentsClient` 仍然能工作。
GooglePatentsClient = GooglePatentsScraper

__all__ = ["GooglePatentsClient", "GooglePatentsScraper"]
