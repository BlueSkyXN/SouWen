# Changelog

## v0.4.0 (unreleased)

### 新增
- 11 个新搜索引擎：SerpAPI、Firecrawl、Perplexity Sonar、Linkup、ScrapingDog、Startpage、Baidu、Mojeek、Yandex、Whoogle、Websurfx
- 67 个 mock 测试（pytest-httpx），覆盖 OpenAlex、Crossref、ArXiv、PatentsView、PQAI、Web 聚合搜索
- 代理池轮换（`proxy_pool` 配置 + 随机选取）
- Playwright 浏览器实例池化（`_BrowserPool` 单例复用 Chromium）
- 抽象限流器接口 `RateLimiterBase(ABC)`，支持 Redis 等分布式限流器扩展
- 全局并发度控制 `asyncio.Semaphore(10)`，防止连接过载
- CLI 搜索结果显示失败源警告

### 修复
- 所有 8 个论文客户端 `total=` → `total_results=`（Pydantic v2 静默忽略 bug）
- 所有 8 个论文客户端 `extra=` → `raw=`（元数据丢失 bug）
- OpenAlex 配置字段名 `openalex_mailto` → `openalex_email`
- ConfigError 构造函数签名错误（TypeError 崩溃）
- ArXiv/PubMed XML 解析崩溃保护（try/except ET.ParseError）
- PubMed 整数转换、除零、分页计算
- Google URL 解码空值 IndexError
- Scraper Retry-After 解析崩溃 + 120s 上限
- EPO OPS range 计算安全
- PDF 获取器 BOM 容忍、窄异常捕获
- YAML 配置加载器支持嵌套和扁平两种格式

### 改进
- 会话缓存从同步 sqlite3 迁移到异步 aiosqlite
- 浏览器指纹库从 3 个扩展到 10 个（Chrome + Edge + Safari + Android）
- 异常处理区分 ConfigError / RateLimitError / 其他
- 所有论文客户端填充 journal/venue 字段
- Pydantic 模型添加 `extra="forbid"` 防止字段名拼写错误
- 统一版本号为单一来源 `__version__`
- Web API 客户端添加 JSON 解析保护
- 数据源列表抽取为共享常量 `ALL_SOURCES`
- HTTP-date Retry-After 解析兼容
- OAuth 响应 KeyError 保护
- TokenBucketLimiter rate 合法性校验

### 依赖
- 新增 `aiosqlite>=0.20.0`

## v0.3.0

### 新功能
- **YAML 配置**: 支持 `souwen.yaml` 配置文件，优先级 env > yaml > .env > 默认值
- **CLI 工具**: `souwen` 命令行工具，支持 `search paper/patent/web`, `config show/init`, `sources`, `serve`
- **FastAPI 服务**: REST API 端点 `/api/v1/search/{paper,patent,web}`, OpenAPI 文档自动生成
- **统一搜索门面**: `search()`, `search_papers()`, `search_patents()` 一个函数搞定
- **web_search() 增强**: engine_map 补全全部 10 个引擎（5 爬虫 + 5 API）

### 修复
- 版本号统一为 0.3.0（pyproject.toml / __init__.py / User-Agent）
- ruff 未使用导入修复

### 依赖
- 新增: `typer>=0.12`, `pyyaml>=6.0`
- 新增可选: `fastapi>=0.111`, `uvicorn[standard]>=0.29`（server extras）

## [0.2.0] - 2026-04-04

### Added
- **常规网页搜索模块** (`souwen.web`) — 10 个搜索引擎
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
