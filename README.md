# SouWen 搜文

> 面向 AI Agent 的学术论文 + 专利信息统一获取工具库

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 🎯 简介

SouWen（搜文）是一个 Python 工具库，为 AI Agent 提供统一的学术论文和专利信息检索接口。它整合了 16 个数据源，将不同 API 的返回结果归一化为统一的 Pydantic v2 数据模型，让 AI Agent 无需关心底层数据源差异。

### 核心特性

- **16 个数据源**：8 个论文源 + 8 个专利源，覆盖全球主要学术和专利数据库
- **统一数据模型**：所有数据源返回 `PaperResult` / `PatentResult`，结构一致
- **零配置即用**：6 个数据源无需 API Key（OpenAlex、Crossref、arXiv、DBLP、PatentsView、PQAI）
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
├── pyproject.toml
├── .env.example
├── src/souwen/
│   ├── __init__.py
│   ├── config.py           # 统一配置管理
│   ├── models.py           # Pydantic v2 数据模型
│   ├── exceptions.py       # 异常体系
│   ├── rate_limiter.py     # 限流器（令牌桶 + 滑动窗口）
│   ├── http_client.py      # httpx async + OAuth 2.0
│   ├── paper/              # 8 个论文数据源
│   ├── patent/             # 8 个专利数据源
│   └── scraper/            # 爬虫兜底层
├── tests/
├── examples/
└── local/                  # 设计文档（不纳入包）
```

## 🧪 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码格式检查
ruff check src/

# 运行示例
python examples/search_papers.py
python examples/search_patents.py
```

## 📝 设计原则

1. **AI Agent 友好**：统一数据模型，结构化输出，最小化 Token 消耗
2. **渐进式配置**：无需 Key 的数据源开箱即用，需要 Key 的友好报错并给出注册指引
3. **稳健性**：自动重试、限流保护、优雅降级
4. **可观测性**：结构化日志，请求耗时追踪

## 📄 License

MIT
