"""fetch/ — 内容抓取横切能力（临时 re-export）

fetch 不是业务 domain 而是横切能力。任何 URL 都可抓。提供者（provider）而非
"搜索某类内容的源"。17 个抓取提供者分别是：
  - builtin (httpx + trafilatura)
  - jina_reader / arxiv_fulltext / crawl4ai / scrapling / newspaper / readability
  - site_crawler / mcp / deepwiki / scrapfly / diffbot / scrapingbee
  - zenrows / scraperapi / apify / cloudflare

跨域提供者（主 domain 不是 fetch，但也能抓）：
  - wayback (domain=archive)
  - tavily / exa / firecrawl / xcrawl (domain=web)
"""

from souwen.web.fetch import fetch_content

__all__ = ["fetch_content"]
