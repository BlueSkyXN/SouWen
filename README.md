# SouWen 搜文

> 面向 AI Agent 的学术论文 + 专利 + 网页信息统一获取工具库

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)

**作者**: [@BlueSkyXN](https://github.com/BlueSkyXN) · **项目地址**: [github.com/BlueSkyXN/SouWen](https://github.com/BlueSkyXN/SouWen) · **协议**: [GPLv3](LICENSE)

> **⚠️ 声明：本项目仅供 Python 学习与技术研究使用。**
> 涵盖的学习方向包括：API 对接与聚合、全栈开发（FastAPI + React）、爬虫技术（TLS 指纹模拟 / 浏览器池化 / 反爬绕过）、CLI 开发（Rich / Click）、异步编程（asyncio / httpx）等。
> 请勿将本项目用于任何违反相关法律法规或第三方服务条款的用途。

## 🎯 简介

SouWen（搜文）为 AI Agent 提供统一的学术论文、专利和网页搜索接口，整合 **58 个数据源**，归一化为 Pydantic v2 数据模型。

- **8 论文源 + 8 专利源 + 21 搜索引擎** — 18 个零配置即用（5 论文 + 2 专利 + 9 爬虫 + 2 自建）
- **统一数据模型** — `PaperResult` / `PatentResult` / `WebSearchResult`
- **异步优先** — httpx async + `asyncio.Semaphore` 全局并发控制
- **智能限流** — 令牌桶 + 滑动窗口，每源独立限流
- **反爬绕过** — TLS 指纹模拟 + 浏览器池化 + 自适应退避
- **PDF 回退链** — 5 级降级策略自动获取全文
- **网页内容抓取** — 16 个提供者（5 零配置 + Jina Reader 免费层 + 10 API），SSRF 防护

## 📦 安装

```bash
pip install souwen

# 如需 TLS 指纹模拟（curl-cffi，可选；缺失时自动回退 httpx）
pip install souwen[tls]

# 如需 Google Patents 爬虫（Playwright 动态渲染 + curl-cffi）
pip install souwen[scraper]

# 如需网页内容抓取（trafilatura 提取 + Markdown 转换）
pip install souwen[web]
```

> `curl-cffi` 已从核心依赖移至可选 extras（`tls` / `scraper`）。未安装时 SouWen 会自动回退到 httpx，TLS 指纹模拟特性会被禁用。

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

    # 并发多引擎聚合（默认 DuckDuckGo + Bing；可通过 engines=[...] 自定义）
    resp = await web_search("machine learning tutorial", max_results_per_engine=5)
    for r in resp.results:
        print(f"[{r.engine}] {r.title} → {r.url}")

asyncio.run(main())
```

### 网页内容抓取（零配置）

```python
import asyncio
from souwen.web.fetch import fetch_content

async def main():
    resp = await fetch_content(
        urls=["https://example.com/article"],
        providers=["builtin"],
        timeout=30.0,
    )
    for r in resp.results:
        if r.error:
            print(f"失败: {r.url} — {r.error}")
        else:
            print(f"标题: {r.title}")
            print(f"内容: {r.content[:200]}...")

asyncio.run(main())
```

## 📚 文档

| 文档 | 内容 |
|------|------|
| [数据源详情](docs/data-sources.md) | 58 个数据源完整列表、分级说明 |
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

**双密码鉴权**（v0.6.3+）：服务端支持访客 / 管理双密码分离，互不影响：

```env
SOUWEN_VISITOR_PASSWORD=visitor-secret   # 保护搜索端点 (/api/v1/search/*)
SOUWEN_ADMIN_PASSWORD=admin-secret       # 保护管理端点 (/api/v1/admin/*)
# 旧版 SOUWEN_API_PASSWORD 仍受支持，作为两者均未设置时的统一回退值（向后兼容）
```

> 管理密码同时可访问搜索端点（admin 是 visitor 的超集）；密码均未配置时端点开放访问，但 admin 端点要求显式 `SOUWEN_ADMIN_OPEN=1` 才会开放。

→ 全部配置字段见 [配置详解](docs/configuration.md)

## 🐳 Docker 部署

### 标准 Docker

```bash
# 构建（Docker 默认包含所有皮肤，支持运行时切换）
docker build -t souwen .

# 运行（可选：设置 API 密码和配置）
# 推荐使用双密码：访客密码保护搜索端点，管理密码保护 /api/v1/admin/*
docker run -d -p 49265:49265 \
  -e SOUWEN_VISITOR_PASSWORD=visitor-secret \
  -e SOUWEN_ADMIN_PASSWORD=admin-secret \
  -v souwen-data:/app/data \
  souwen

# 或使用旧版统一密码（同时作为访客与管理密码的回退值，向后兼容）
# docker run -d -p 49265:49265 -e SOUWEN_API_PASSWORD=your-secret souwen

# 或使用 docker compose
docker compose up -d
```

### HuggingFace Spaces

将 `cloud/hfs/` 目录内容推送到 HF Space 仓库（SDK 类型选 Docker）。通过 Space Settings → Variables 设置 `SOUWEN_CONFIG_B64`（base64 编码的 souwen.yaml）。

### ModelScope 创空间

将 `cloud/modelscope/` 目录内容推送到 ModelScope 创空间仓库。端口固定为 7860。

→ 部署后访问 `/panel` 进入管理面板，`/health` 检查健康状态，`/docs` 查看 API 文档。

## 🎨 前端管理面板

管理面板 (`/panel`) 基于 React + TypeScript + SCSS Modules + Framer Motion 构建，采用**多皮肤架构**，支持**运行时皮肤切换**。

### 三层分离

```
Skin（皮肤）→ Mode（模式）→ Scheme（配色）
│                │              │
│                │              └── 每皮肤独立配色（运行时切换）
│                └── light / dark（运行时切换）
└── souwen-classic / carbon / apple / ios（构建时选择或运行时切换）
```

- **Skin** = 完全独立的前端 UI（布局、组件、路由、交互逻辑），目前提供 4 套：
  - `souwen-classic` — 经典默认皮肤（多层阴影 + hover 提升）
  - `carbon` — 暗色科技风（辉光 + 扫描线）
  - `apple` — Apple 风格（毛玻璃 + 大圆角）
  - `ios` — iOS 风格（hairline 分割线 + 弹性过渡）
- **Mode** = 明暗模式（light/dark），面板内切换
- **Scheme** = 强调色方案，每皮肤独立定义，面板内切换

### 构建模式

通过 `VITE_SKINS` 环境变量控制构建模式（默认全皮肤）：

| 模式 | 命令 | 说明 |
|------|------|------|
| 全皮肤（默认） | `npm run build` | 包含全部 4 套皮肤，支持运行时切换 |
| 单皮肤（classic） | `npm run build:classic` | 仅含 souwen-classic，体积最小 |
| 单皮肤（carbon） | `npm run build:carbon` | 仅含 carbon |
| 单皮肤（apple/ios） | `VITE_SKINS=apple npm run build` 或 `VITE_SKINS=ios npm run build` | 仅含指定皮肤 |
| 指定多皮肤 | `VITE_SKINS=souwen-classic,carbon npm run build` | 包含逗号分隔的皮肤集合 |

多皮肤构建时，面板内会显示「切换皮肤」按钮。

### 前端开发

```bash
cd panel

# 开发模式（默认全皮肤，可运行时切换）
npm run dev

# 单皮肤开发
npm run dev:classic
npm run dev:carbon
VITE_SKINS=apple npm run dev   # apple 皮肤
VITE_SKINS=ios npm run dev     # ios 皮肤

# 构建产物（单文件 HTML，自动复制到 src/souwen/server/panel.html）
npm run build            # 默认全皮肤
npm run build:classic    # 单皮肤（体积更小）

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
souwen fetch https://example.com -p builtin       # 内容抓取（默认 builtin）
souwen fetch https://a.com https://b.com --json    # 批量抓取 JSON 输出
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
