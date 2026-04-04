# Changelog

## [0.2.0] - 2026-04-04

### Added
- **常规网页搜索模块** (`souwen.web`) — 10 个搜索引擎
  - 移植自 [SoSearch](https://github.com/NetLops/SoSearch) Rust 项目 + 扩展
  - **爬虫类（无需 Key，零配置即用）**
    - DuckDuckGoClient — DuckDuckGo HTML 搜索（uddg= URL 解码）
    - YahooClient — Yahoo 搜索（Bing 驱动，RU=/RK= URL 解码）
    - BraveClient — Brave 独立索引搜索
    - GoogleClient — Google 搜索（高风险，TLS 指纹 + 多 snippet 选择器）
    - BingClient — Bing 搜索（li.b_algo 选择器）
  - **API 类（需 Key / 自建实例）**
    - SearXNGClient — SearXNG 元搜索（一个接入 = 250+ 引擎）
    - TavilyClient — Tavily AI 搜索（为 Agent 设计，内置内容提取）
    - ExaClient — Exa 语义搜索（神经索引 + find_similar）
    - SerperClient — Serper Google SERP API（含 Knowledge Graph）
    - BraveApiClient — Brave 官方 REST API（免费 2000 次/月）
  - `web_search()` — 并发多引擎聚合搜索（asyncio.gather + URL 去重）
- **新数据模型**
  - `WebSearchResult` — 统一网页搜索结果模型
  - 10 个 `SourceType.WEB_*` 枚举值
- **新配置项**
  - `searxng_url` / `tavily_api_key` / `exa_api_key` / `serper_api_key` / `brave_api_key`
- **过盾特性**
  - 所有爬虫引擎基于 `BaseScraper`（curl_cffi TLS 指纹 + 浏览器头）
  - Google/Bing 专门调优延迟和重试策略

### Fixed
- `BaseScraper.close()` 中 curl_cffi `AsyncSession.close()` 缺少 `await`（资源泄漏）

## [0.1.0] - 2026-04-03

### Added
- 项目初始化
- **基础设施层**
  - `config.py` — 统一配置管理（环境变量 / .env / 默认值）
  - `models.py` — Pydantic v2 统一数据模型（PaperResult, PatentResult, SearchResponse）
  - `exceptions.py` — 6 类自定义异常体系
  - `rate_limiter.py` — 令牌桶 + 滑动窗口限流器
  - `http_client.py` — httpx async 统一客户端 + OAuth 2.0 Token 自动管理
- **8 个论文数据源**
  - OpenAlex (无需 Key)
  - Semantic Scholar (可选 Key，含 TLDR)
  - Crossref (无需 Key，DOI 权威源)
  - arXiv (无需 Key，Atom XML 解析，全文免费)
  - DBLP (无需 Key，计算机科学权威)
  - CORE (需 Key，开放获取)
  - PubMed (可选 Key，两步 XML 检索)
  - Unpaywall (需 Email，OA PDF 查找)
  - PDF 回退链获取器 (5 级降级策略)
- **8 个专利数据源**
  - PatentsView (无需 Key，USPTO 数据)
  - PQAI (无需 Key，语义检索)
  - EPO OPS (OAuth 2.0，CQL 检索)
  - USPTO ODP (API Key)
  - The Lens (Bearer Token，动态限流)
  - CNIPA (OAuth 2.0，中国专利)
  - PatSnap (API Key，172 司法管辖区)
  - Google Patents (爬虫兜底)
- **爬虫层**
  - `BaseScraper` — 礼貌爬取基类（自适应限速、UA 轮换）
  - `GooglePatentsScraper` — Google Patents 爬虫实现
- **示例和测试**
  - `examples/search_papers.py` — 论文搜索示例
  - `examples/search_patents.py` — 专利搜索示例
  - 15 个基础设施层单元测试
