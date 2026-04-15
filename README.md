# SouWen 搜文

> 面向 AI Agent 的学术论文 + 专利 + 网页信息统一获取工具库

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)

> **⚠️ 声明：本项目仅供 Python 学习与技术研究使用。**
> 涵盖的学习方向包括：API 对接与聚合、全栈开发（FastAPI + React）、爬虫技术（TLS 指纹模拟 / 浏览器池化 / 反爬绕过）、CLI 开发（Rich / Click）、异步编程（asyncio / httpx）等。
> 请勿将本项目用于任何违反相关法律法规或第三方服务条款的用途。

## 🎯 简介

SouWen（搜文）为 AI Agent 提供统一的学术论文、专利和网页搜索接口，整合 **37 个数据源**，归一化为 Pydantic v2 数据模型。

- **8 论文源 + 8 专利源 + 21 搜索引擎** — 22 个零配置即用
- **统一数据模型** — `PaperResult` / `PatentResult` / `WebSearchResult`
- **异步优先** — httpx async + `asyncio.Semaphore` 全局并发控制
- **智能限流** — 令牌桶 + 滑动窗口，每源独立限流
- **反爬绕过** — TLS 指纹模拟 + 浏览器池化 + 自适应退避
- **PDF 回退链** — 5 级降级策略自动获取全文

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
    async with OpenAlexClient() as client:
        results = await client.search("deep learning network security", per_page=5)
        for paper in results.results:
            print(f"{paper.title} ({paper.year}) 引用:{paper.citation_count}")

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
    async with PatentsViewClient() as client:
        results = await client.search_by_assignee("Huawei", per_page=5)
        for patent in results.results:
            print(f"{patent.patent_id}: {patent.title}")

    async with PqaiClient() as client:
        results = await client.search("wireless authentication using ML", n_results=5)
        for patent in results.results:
            print(f"{patent.patent_id}: {patent.title}")

asyncio.run(main())
```

### 网页搜索（无需 Key）

```python
import asyncio
from souwen.web import DuckDuckGoClient, web_search

async def main():
    async with DuckDuckGoClient() as client:
        results = await client.search("Python asyncio", max_results=5)
        for r in results.results:
            print(f"{r.title} → {r.url}")

    # 并发多引擎聚合（DuckDuckGo + Yahoo + Brave）
    resp = await web_search("machine learning tutorial", max_results_per_engine=5)
    for r in resp.results:
        print(f"[{r.engine}] {r.title} → {r.url}")

asyncio.run(main())
```

## 📚 文档

| 文档 | 内容 |
|------|------|
| [数据源详情](docs/data-sources.md) | 37 个数据源完整列表、分级说明 |
| [配置详解](docs/configuration.md) | 配置优先级、全部字段、代理池、YAML 格式 |
| [架构设计](docs/architecture.md) | 数据流、基类模式、限流器、异常体系、项目结构 |
| [外观定制](docs/appearance.md) | 皮肤、明暗模式、配色方案、自定义皮肤指南 |
| [反爬技术栈](docs/anti-scraping.md) | TLS 指纹、浏览器池化、自适应退避 |
| [API 参考](docs/api-reference.md) | Python API、数据模型、CLI 命令、MCP 工具 |
| [贡献指南](docs/contributing.md) | 添加数据源、测试、代码风格、PR 流程 |

## 📊 数据源

**论文**（8 源）：OpenAlex、Semantic Scholar、Crossref、arXiv、DBLP、CORE、PubMed、Unpaywall — 其中 5 个零配置

**专利**（8 源）：PatentsView、PQAI、EPO OPS、USPTO ODP、The Lens、CNIPA、PatSnap、Google Patents — 其中 2 个零配置

**搜索引擎**（21 个）：9 个爬虫（DuckDuckGo、Yahoo、Brave 等）+ 10 个 API（Tavily、Exa、SearXNG 等）+ 2 个自建实例

→ 完整列表见 [数据源详情](docs/data-sources.md)

## ⚙️ 配置

配置优先级：环境变量 > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > 默认值

```bash
souwen config init   # 生成 YAML 模板
souwen config show   # 查看当前配置
```

推荐配置（进入 polite pool 获得更快响应）：

```env
SOUWEN_OPENALEX_EMAIL=your@email.com
SOUWEN_UNPAYWALL_EMAIL=your@email.com
```

→ 全部配置字段见 [配置详解](docs/configuration.md)

## 🐳 Docker 部署

### 标准 Docker

```bash
# 构建（默认皮肤 souwen-classic）
docker build -t souwen .

# 使用自定义皮肤构建
docker build -t souwen --build-arg SKIN=souwen-classic .

# 运行（可选：设置 API 密码和配置）
docker run -d -p 49265:49265 \
  -e SOUWEN_API_PASSWORD=your-secret \
  -v souwen-data:/app/data \
  souwen

# 或使用 docker compose
docker compose up -d
```

### HuggingFace Spaces

将 `cloud/hfs/` 目录内容推送到 HF Space 仓库（SDK 类型选 Docker）。通过 Space Settings → Variables 设置 `SOUWEN_CONFIG_B64`（base64 编码的 souwen.yaml）。

### ModelScope 创空间

将 `cloud/modelscope/` 目录内容推送到 ModelScope 创空间仓库。端口固定为 7860。

→ 部署后访问 `/panel` 进入管理面板，`/health` 检查健康状态，`/docs` 查看 API 文档。

## 🎨 前端管理面板

管理面板 (`/panel`) 基于 React + TypeScript + SCSS Modules + Framer Motion 构建，采用**多皮肤架构**。

### 三层分离

```
Skin（皮肤）→ Mode（模式）→ Scheme（配色）
│                │              │
│                │              └── nebula / aurora / obsidian（运行时切换）
│                └── light / dark（运行时切换）
└── souwen-classic / ...（构建时选择）
```

- **Skin** = 完全独立的前端 UI（布局、组件、路由、交互逻辑）
- **Mode** = 明暗模式（light/dark），面板内切换
- **Scheme** = 强调色方案（星云/极光/黑曜石），面板内切换

### 前端开发

```bash
cd panel

# 开发模式（默认 souwen-classic 皮肤）
npm run dev:classic

# 构建产物（单文件 HTML，自动复制到 src/souwen/server/panel.html）
npm run build:classic

# 使用其他皮肤
VITE_SKIN=my-skin npm run dev

# 测试
npm test
```

### 目录结构

```
panel/src/
  core/           # 跨皮肤共享（stores, API, types, i18n, lib）
  skins/
    souwen-classic/  # 默认皮肤
      components/    # UI 组件
      pages/         # 页面
      styles/        # SCSS 样式
      stores/        # 皮肤状态
      routes.tsx     # 路由定义
      skin.config.ts # 皮肤配置（配色方案等）
      index.ts       # 皮肤入口
```

## 🛠️ 高级用法

```bash
souwen search paper "transformer" -n 5          # 论文搜索
souwen search patent "lithium battery" -s pqai   # 专利搜索
souwen search web "Python asyncio" --json        # 网页搜索（JSON 输出）
souwen sources                                    # 查看数据源
souwen doctor                                     # 健康检查
souwen serve --port 8000                          # 启动 API 服务
python -m souwen.integrations.mcp_server          # MCP 工具服务
```

→ 完整 API 和 CLI 文档见 [API 参考](docs/api-reference.md)

## 🧪 开发

```bash
pip install -e ".[dev]"           # 安装后端开发依赖
pytest tests/ -v                  # 运行后端测试
ruff check src/                   # 代码检查
ruff format --check src/          # 格式检查

cd panel && npm install           # 安装前端依赖
npm run dev:classic               # 前端开发服务器
npm test                          # 前端测试
npm run build:classic             # 前端构建
```

→ 贡献代码见 [贡献指南](docs/contributing.md)

## 📄 License

GPL-3.0-or-later
