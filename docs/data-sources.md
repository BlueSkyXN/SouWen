# 数据源详情

> SouWen 支持的全部 37 个数据源

## 概览

| 类别 | 数量 | 免费可用 | 需要 Key |
|------|------|----------|----------|
| 论文 | 8 | 5（OpenAlex、Crossref、arXiv、DBLP、PubMed） | 3（Semantic Scholar 可选、CORE、Unpaywall） |
| 专利 | 8 | 2（PatentsView、PQAI） | 6（EPO、USPTO ODP、The Lens、CNIPA、PatSnap、Google Patents 爬虫） |
| 搜索引擎 | 21 | 9（爬虫类） + 2（自建实例） | 10（API 类） |

## 论文数据源

| 数据源 | 客户端类 | 鉴权 | 特点 |
|--------|---------|------|------|
| OpenAlex | `OpenAlexClient` | 无需 Key | 最全面的开放学术数据，2.5 亿篇文献 |
| Semantic Scholar | `SemanticScholarClient` | 可选 Key | AI 生成 TLDR 摘要，语义搜索 |
| Crossref | `CrossrefClient` | 无需 Key | DOI 元数据权威源，1.5 亿条记录 |
| arXiv | `ArxivClient` | 无需 Key | 全文免费预印本，支持高级检索语法 |
| DBLP | `DblpClient` | 无需 Key | 计算机科学权威索引 |
| CORE | `CoreClient` | 需 Key | 开放获取聚合平台，全文检索 |
| PubMed | `PubMedClient` | 可选 Key | 生物医学权威数据库 |
| Unpaywall | `UnpaywallClient` | 需 Email | OA PDF 查找，需提供邮箱作为标识 |

### 分级说明

- **Tier 1（零配置）**：OpenAlex、Crossref、arXiv、DBLP — 无需任何配置即可使用
- **Tier 2（推荐配置）**：PubMed（可选 Key 提高速率）、Semantic Scholar（可选 Key 提高速率）、Unpaywall（需 Email）
- **Tier 3（需注册）**：CORE（需申请 API Key）

## 专利数据源

| 数据源 | 客户端类 | 鉴权 | 特点 |
|--------|---------|------|------|
| PatentsView | `PatentsViewClient` | 无需 Key | USPTO 专利数据，RESTful API |
| PQAI | `PqaiClient` | 无需 Key | 语义检索，支持自然语言输入 |
| EPO OPS | `EpoOpsClient` | OAuth 2.0 | 欧洲专利局，CQL 检索语法 |
| USPTO ODP | `UsptoOdpClient` | API Key | USPTO 官方数据门户，全量数据 |
| The Lens | `TheLensClient` | Bearer Token | 专利-学术交叉引用分析 |
| CNIPA | `CnipaClient` | OAuth 2.0 | 中国知识产权局 |
| PatSnap | `PatSnapClient` | API Key | 覆盖 172 个司法管辖区 |
| Google Patents | `GooglePatentsClient` | 爬虫 | 兜底方案，需 Playwright |

### 分级说明

- **Tier 1（零配置）**：PatentsView、PQAI — 无需任何配置
- **Tier 2（OAuth）**：EPO OPS（需注册获取 Consumer Key/Secret）、CNIPA（需注册获取 Client ID/Secret）
- **Tier 3（API Key）**：USPTO ODP、The Lens、PatSnap — 需申请 API Key
- **Tier 4（爬虫）**：Google Patents — 需安装 `souwen[scraper]`

## 网页搜索引擎

### 爬虫类（无需 Key，零配置即用）

| 引擎 | 客户端类 | 鉴权 | 特点 |
|------|---------|------|------|
| DuckDuckGo | `DuckDuckGoClient` | 无需 Key | HTML 轻量版，无 JS 依赖 |
| Yahoo | `YahooClient` | 无需 Key | Bing 驱动，对 DC IP 宽容 |
| Brave | `BraveClient` | 无需 Key | 独立索引，隐私友好 |
| Google | `GoogleClient` | 无需 Key | 高风险，建议配代理 |
| Bing | `BingClient` | 无需 Key | 反爬宽松，微软生态 |
| Startpage | `StartpageClient` | 无需 Key | Google 代理，隐私友好 |
| Baidu | `BaiduClient` | 无需 Key | 中文搜索首选 |
| Mojeek | `MojeekClient` | 无需 Key | 独立索引，英国引擎 |
| Yandex | `YandexClient` | 无需 Key | 俄语搜索首选 |

### API 类（需 Key）

| 服务 | 客户端类 | 鉴权 | 特点 |
|------|---------|------|------|
| SearXNG | `SearXNGClient` | 实例 URL | 一个接入 = 250+ 引擎 |
| Tavily | `TavilyClient` | API Key | AI Agent 原生设计 |
| Exa | `ExaClient` | API Key | 语义搜索（神经索引） |
| Serper | `SerperClient` | API Key | Google 结构化 JSON |
| Brave API | `BraveApiClient` | API Key | 官方 REST API，免费 2000 次/月 |
| SerpAPI | `SerpApiClient` | API Key | 多引擎 SERP 结构化数据 |
| Firecrawl | `FirecrawlClient` | API Key | 网页爬取 + 内容提取 |
| Perplexity Sonar | `PerplexitySonarClient` | API Key | AI 搜索，带引用来源 |
| Linkup | `LinkupClient` | API Key | 聚合搜索 API |
| ScrapingDog | `ScrapingDogClient` | API Key | SERP 代理抓取 |

### 自建实例类（仅需 URL）

| 服务 | 客户端类 | 鉴权 | 特点 |
|------|---------|------|------|
| Whoogle | `WhoogleClient` | 实例 URL | 自托管 Google 前端，无追踪 |
| Websurfx | `WebsurfxClient` | 实例 URL | 自托管元搜索引擎 |

### 聚合搜索

| 功能 | 函数 | 说明 |
|------|------|------|
| 聚合搜索 | `web_search()` | 并发多引擎搜索 + URL 去重 |

默认使用 DuckDuckGo + Yahoo + Brave 三引擎并发，可通过 `engines` 参数自定义组合。
