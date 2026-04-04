# SouWen 搜文

> 面向 AI Agent 的学术论文 + 专利 + 网页信息统一获取工具库

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 🎯 简介

SouWen（搜文）是一个 Python 工具库，为 AI Agent 提供统一的学术论文、专利信息和网页搜索接口。它整合了 26 个数据源，将不同 API 的返回结果归一化为统一的 Pydantic v2 数据模型，让 AI Agent 无需关心底层数据源差异。

### 核心特性

- **26 个数据源**：8 个论文源 + 8 个专利源 + 10 个搜索引擎，覆盖全球主要学术和专利数据库及网页搜索
- **统一数据模型**：所有数据源返回 `PaperResult` / `PatentResult` / `WebSearchResult`，结构一致
- **零配置即用**：13 个数据源无需 API Key（OpenAlex、Crossref、arXiv、DBLP、PatentsView、PQAI + DuckDuckGo、Yahoo、Brave、Google、Bing）
- **异步优先**：全面使用 `httpx` async，支持高并发
- **智能限流**：令牌桶 + 滑动窗口，每个数据源独立限流
- **PDF 回退链**：5 级降级策略自动获取全文 PDF
- **OAuth 自动管理**：EPO OPS / CNIPA Token 自动刷新

## 📦 安装

```bash
pip install souwen

# 如需 Google Patents 爬虫（Playwright 动态渲染）
pip install souwen[scraper]
```

## 🚀 快速开始

### 论文搜索（无需 Key）

```python
import asyncio
from souwen.paper import OpenAlexClient, ArxivClient

async def main():
    # OpenAlex 搜索
    async with OpenAlexClient() as client:
        results = await client.search("deep learning network security", per_page=5)
        for paper in results.results:
            print(f"{paper.title} ({paper.year}) 引用:{paper.citation_count}")

    # arXiv 搜索（所有论文全文免费）
    async with ArxivClient() as client:
        results = await client.search("cat:cs.AI AND ti:transformer", max_results=5)
        for paper in results.results:
            print(f"{paper.title} → {paper.pdf_url}")

asyncio.run(main())
```

### 专利搜索（无需 Key）

```python
import asyncio
from souwen.patent import PatentsViewClient, PqaiClient

async def main():
    # PatentsView 搜索美国专利
    async with PatentsViewClient() as client:
        results = await client.search_by_assignee("Huawei", per_page=5)
        for patent in results.results:
            print(f"{patent.patent_id}: {patent.title}")

    # PQAI 语义搜索
    async with PqaiClient() as client:
        results = await client.search("wireless authentication using ML", n_results=5)
        for patent in results.results:
            print(f"{patent.patent_id}: {patent.title}")

asyncio.run(main())
```

### 网页搜索（无需 Key，移植自 SoSearch）

```python
import asyncio
from souwen.web import DuckDuckGoClient, web_search

async def main():
    # 单引擎搜索
    async with DuckDuckGoClient() as client:
        results = await client.search("Python asyncio", max_results=5)
        for r in results.results:
            print(f"{r.title} → {r.url}")

    # 并发多引擎聚合搜索（DuckDuckGo + Yahoo + Brave）
    resp = await web_search("machine learning tutorial", max_results_per_engine=5)
    for r in resp.results:
        print(f"[{r.engine}] {r.title} → {r.url}")

asyncio.run(main())
```

### CLI 命令行

```bash
# 搜索论文
souwen search paper "transformer attention" -n 5

# 搜索专利
souwen search patent "lithium battery" -s patentsview,pqai

# 搜索网页
souwen search web "Python asyncio" -e duckduckgo,brave

# JSON 输出（适合管道处理）
souwen search paper "deep learning" --json | jq '.[]'

# 查看所有数据源
souwen sources

# 显示配置
souwen config show

# 生成配置模板
souwen config init
```

### API 服务

```bash
# 安装 server 依赖
pip install souwen[server]

# 启动服务（默认 :8000）
souwen serve --port 8000

# 调用 API
curl "http://localhost:8000/api/v1/search/paper?q=transformer&per_page=5"
curl "http://localhost:8000/api/v1/search/web?q=Python&engines=duckduckgo,brave"
curl "http://localhost:8000/api/v1/sources"

# OpenAPI 文档
open http://localhost:8000/docs
```

### YAML 配置

支持通过 `souwen.yaml` 配置（优先级: 环境变量 > ./souwen.yaml > ~/.config/souwen/config.yaml > .env > 默认值）:

```bash
souwen config init  # 生成模板
```

### PDF 全文获取

```python
from souwen.paper import OpenAlexClient, fetch_pdf

async with OpenAlexClient() as client:
    results = await client.search("attention is all you need", per_page=1)
    paper = results.results[0]

    # 5 级回退链自动获取 PDF
    pdf_path = await fetch_pdf(paper)
    if pdf_path:
        print(f"PDF 已下载: {pdf_path}")
```

## 📊 数据源一览

### 论文数据源

| 数据源 | 客户端类 | 鉴权 | 特点 |
|--------|---------|------|------|
| OpenAlex | `OpenAlexClient` | 无需 Key | 最全面的开放学术数据 |
| Semantic Scholar | `SemanticScholarClient` | 可选 Key | AI 生成 TLDR 摘要 |
| Crossref | `CrossrefClient` | 无需 Key | DOI 元数据权威源 |
| arXiv | `ArxivClient` | 无需 Key | 全文免费，预印本 |
| DBLP | `DblpClient` | 无需 Key | 计算机科学权威索引 |
| CORE | `CoreClient` | 需 Key | 开放获取聚合 |
| PubMed | `PubMedClient` | 可选 Key | 生物医学权威 |
| Unpaywall | `UnpaywallClient` | 需 Email | OA PDF 查找 |

### 专利数据源

| 数据源 | 客户端类 | 鉴权 | 特点 |
|--------|---------|------|------|
| PatentsView | `PatentsViewClient` | 无需 Key | USPTO 专利数据 |
| PQAI | `PqaiClient` | 无需 Key | 语义检索，自然语言输入 |
| EPO OPS | `EpoOpsClient` | OAuth 2.0 | 欧洲专利局，CQL 检索 |
| USPTO ODP | `UsptoOdpClient` | API Key | USPTO 全量数据 |
| The Lens | `TheLensClient` | Bearer Token | 专利-学术交叉引用 |
| CNIPA | `CnipaClient` | OAuth 2.0 | 中国知识产权局 |
| PatSnap | `PatSnapClient` | API Key | 172 司法管辖区 |
| Google Patents | `GooglePatentsClient` | 爬虫 | 兜底方案 |

### 网页搜索引擎（10 个，含爬虫 + API）

#### 爬虫类（无需 Key，零配置即用）

| 引擎 | 客户端类 | 鉴权 | 特点 |
|------|---------|------|------|
| DuckDuckGo | `DuckDuckGoClient` | 无需 Key | HTML 轻量版，无 JS 依赖 |
| Yahoo | `YahooClient` | 无需 Key | Bing 驱动，对 DC IP 宽容 |
| Brave | `BraveClient` | 无需 Key | 独立索引，隐私友好 |
| Google | `GoogleClient` | 无需 Key | 高风险，建议配代理 |
| Bing | `BingClient` | 无需 Key | 反爬宽松，微软生态 |

#### API 类（需 Key / 自建实例）

| 服务 | 客户端类 | 鉴权 | 特点 |
|------|---------|------|------|
| SearXNG | `SearXNGClient` | 实例 URL | 一个接入 = 250+ 引擎 |
| Tavily | `TavilyClient` | API Key | AI Agent 原生设计 |
| Exa | `ExaClient` | API Key | 语义搜索（神经索引） |
| Serper | `SerperClient` | API Key | Google 结构化 JSON |
| Brave API | `BraveApiClient` | API Key | 官方 REST API，免费 2000 次/月 |

#### 聚合搜索

| 功能 | 函数 | 说明 |
|------|------|------|
| 聚合搜索 | `web_search()` | 并发三引擎 + URL 去重 |

## ⚙️ 配置

复制 `.env.example` 为 `.env`，按需填写：

```bash
cp .env.example .env
```

配置优先级：环境变量 > `.env` 文件 > `~/.config/souwen/config.toml` > 内置默认值

主要配置项：

```env
# 论文（推荐配置，进入 polite pool 获得更快响应）
SOUWEN_OPENALEX_EMAIL=your@email.com
SOUWEN_UNPAYWALL_EMAIL=your@email.com

# 专利（按需配置）
SOUWEN_EPO_CONSUMER_KEY=your_key
SOUWEN_EPO_CONSUMER_SECRET=your_secret

# 通用
SOUWEN_PROXY=http://proxy:8080    # 代理（可选）
SOUWEN_TIMEOUT=30                  # 超时秒数
```

## 🏗️ 项目结构

```
SouWen/
├── .github/workflows/     # CI/CD (lint + test + publish)
├── pyproject.toml
├── .env.example
├── src/souwen/
│   ├── __init__.py
│   ├── config.py           # 统一配置管理（环境变量 / .env / 默认值）
│   ├── models.py           # Pydantic v2 统一数据模型
│   ├── exceptions.py       # 6 类自定义异常体系
│   ├── rate_limiter.py     # 限流器（令牌桶 + 滑动窗口）
│   ├── http_client.py      # httpx async + OAuth 2.0 Token 自动刷新
│   ├── fingerprint.py      # Chrome TLS 指纹库（绕过 JA3 检测）
│   ├── session_cache.py    # SQLite 会话/Token 持久化缓存
│   ├── retry.py            # 分层重试策略（http/scraper/captcha）
│   ├── paper/              # 8 个论文数据源
│   ├── patent/             # 8 个专利数据源
│   ├── web/                # 10 个搜索引擎（5 爬虫 + 5 API）
│   └── scraper/            # 爬虫兜底层（TLS 指纹 + 礼貌爬取）
├── tests/                  # 单元测试
├── examples/               # 使用示例
│   ├── search_papers.py    # 论文搜索示例
│   ├── search_patents.py   # 专利搜索示例
│   └── search_web.py       # 网页搜索示例
└── local/                  # 设计文档（不纳入包）
```

## 🔒 反爬技术栈

SouWen 集成了完整的反爬绕过方案（移植自 OpenRouter RegBot 项目）：

| 技术 | 说明 | 模块 |
|------|------|------|
| **TLS 指纹模拟** | curl_cffi impersonate Chrome 120/124 | `fingerprint.py` |
| **浏览器请求头** | 13 个头（Sec-CH-UA 系列、Sec-Fetch 系列） | `fingerprint.py` |
| **分层重试** | http (3次) / scraper (5次) / captcha (5次) | `retry.py` |
| **会话缓存** | SQLite 持久化 OAuth Token / Cookie | `session_cache.py` |
| **礼貌爬取** | 随机间隔 + 自适应退避 + 429 处理 | `scraper/base.py` |

> curl_cffi 为可选依赖，未安装时自动回退到 httpx。

## 🛠️ 高级用法

### AI Agent 搜索 API（Tavily / Exa）

```python
from souwen.web import TavilyClient, ExaClient

# Tavily — 为 AI Agent 设计，返回清洗后的内容
async with TavilyClient(api_key="tvly-xxx") as client:
    resp = await client.search("LLM fine-tuning best practices", search_depth="advanced")
    for r in resp.results:
        print(f"{r.title}: {r.snippet[:100]}...")

# Exa — 语义搜索 + 相似页面发现
async with ExaClient(api_key="exa-xxx") as client:
    resp = await client.search("papers about transformer attention mechanisms")
    similar = await client.find_similar("https://arxiv.org/abs/1706.03762")
```

### SearXNG 元搜索（一个接入 = 250+ 引擎）

```python
from souwen.web import SearXNGClient

# 需自建 SearXNG 实例: docker run -p 8888:8080 searxng/searxng
async with SearXNGClient(instance_url="http://localhost:8888") as client:
    resp = await client.search("quantum computing", engines="google,bing,duckduckgo")
```

### 自定义聚合搜索引擎组合

```python
from souwen.web import web_search

# 默认使用 DuckDuckGo + Yahoo + Brave
resp = await web_search("Python tutorial")

# 指定引擎子集（含高风险引擎）
resp = await web_search("Rust vs Go", engines=["duckduckgo", "google", "bing"])
```

## 🧪 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 安装爬虫可选依赖（TLS 指纹模拟）
pip install -e ".[scraper]"

# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/
ruff format --check src/

# 运行示例
python examples/search_papers.py
python examples/search_patents.py
python examples/search_web.py
```

## 📝 设计原则

1. **AI Agent 友好**：统一数据模型，结构化输出，最小化 Token 消耗
2. **渐进式配置**：无需 Key 的数据源开箱即用，需要 Key 的友好报错并给出注册指引
3. **稳健性**：自动重试、限流保护、优雅降级
4. **可观测性**：结构化日志，请求耗时追踪

## 📄 License

MIT
