"""Google Patents 客户端

`GooglePatentsClient` 是 `souwen.providers.runtime_clients.patent.google_patents_scraper.GooglePatentsScraper`
的便捷别名（同一个 HTML + XHR fallback 实现）。提供两条 import 路径：

    from souwen.providers.runtime_clients.patent import GooglePatentsClient
    from souwen.providers.runtime_clients.patent.google_patents_scraper import GooglePatentsScraper
"""

from __future__ import annotations

from souwen.providers.runtime_clients.patent.google_patents_scraper import GooglePatentsScraper

#: 便捷别名，便于 `from souwen.providers.runtime_clients.patent.google_patents import GooglePatentsClient`
GooglePatentsClient = GooglePatentsScraper

__all__ = ["GooglePatentsClient", "GooglePatentsScraper"]
