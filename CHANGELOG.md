# Changelog

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
