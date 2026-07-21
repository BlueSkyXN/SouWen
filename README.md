# SouWen 搜文

**[English](README.en.md)** | 中文

> 面向 AI Agent 和自动化脚本的统一搜索、抓取与归档工具箱。

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0rc1-orange)](CHANGELOG.md)
[![External Smoke Gate](https://github.com/BlueSkyXN/SouWen/actions/workflows/external-smoke-gate.yml/badge.svg)](https://github.com/BlueSkyXN/SouWen/actions/workflows/external-smoke-gate.yml)

**作者**: [@BlueSkyXN](https://github.com/BlueSkyXN) · **项目地址**: [github.com/BlueSkyXN/SouWen](https://github.com/BlueSkyXN/SouWen) · **协议**: [GPLv3](LICENSE)

> **⚠️ 声明：本项目仅供 Python 学习与技术研究使用。** 涵盖 API 聚合、全栈开发（FastAPI + React）、爬虫技术（TLS 指纹 / 反爬绕过）、CLI、异步编程等方向。请勿用于违反法律法规或第三方服务条款的用途。

---

## 📖 目录

- [简介](#-简介)
- [安装](#-安装)
- [快速开始](#-快速开始)
- [配置](#️-配置)
- [架构](#-架构)
- [部署](#-部署)
- [文档](#-文档)
- [贡献](#-贡献)
- [License](#-license)

---

## 🎯 简介

SouWen（搜文）为 AI Agent、CLI 脚本和服务端应用提供统一的多源搜索接口，**所有数据源通过 `SourceAdapter` 单一事实源声明**，归一化为 Pydantic v2 数据模型。

注册表架构使源的新增成本降到 **1-2 处**改动；CLI / API / Panel 均按 domain、capability 和 Source Catalog 组织。

### 特性

<!-- BEGIN AUTO: SOURCE METRICS -->
- **109 个内置 registered source**：正式 Source Catalog 含 **108 个 public** 条目，另有 **1 个 hidden/internal** 条目；外部插件可在运行时追加。
  - 公开源主 domain：`paper` 21 · `patent` 8 · `web` 32 · `social` 5 · `video` 2 · `knowledge` 1 · `developer` 2 · `cn_tech` 9 · `office` 1 · `archive` 1 · `book` 7 · `research_output` 2
  - `fetch` 横切视图：**24 个 provider** = **17 个 fetch 主 domain** + **7 个跨域源**。
<!-- END AUTO: SOURCE METRICS -->
- **统一 Pydantic v2 数据模型**：`PaperResult` / `PatentResult` / `WebSearchResult` / `FetchResult` / `WaybackCDXResponse` / ...
- **异步优先**：httpx + asyncio，per-loop Semaphore 控制并发
- **智能限流**：Token Bucket + 滑动窗口，每源独立
- **curl_cffi TLS 指纹**：15+ 爬虫类源用浏览器指纹伪装过盾
- **WARP 五模式代理**：wireproxy / kernel / usque / warp-cli / external，支持运行时动态安装和管理
- **MCP 协议**：供 Claude Code / Cursor / Windsurf 等 AI 助手直接调用
- **多皮肤 Web UI**：souwen-google（默认）/ souwen-nebula / carbon / apple / ios（SCSS Modules + Zustand）

## 📦 安装

```bash
# 从当前 main 源码线安装核心库 + CLI
git clone https://github.com/BlueSkyXN/SouWen.git
cd SouWen
pip install -e .

# 零 Key / 最小依赖体验（含 MCP client 与 stdio server）
pip install -e ".[edition-basic]"

# 默认 API 服务 + MCP + TLS 指纹 + 网页搜索
pip install -e ".[edition-pro]"

# 完整公共重型能力；crawl4ai 与 scrapling 当前依赖树互斥，浏览器抓取二选一
pip install -e ".[edition-full-crawl4ai]"
pip install -e ".[edition-full-scrapling]"
```

## 🚀 快速开始

### CLI

```bash
# 多源搜索
souwen search paper "transformer"
souwen search patent "quantum computing"
souwen search web "python asyncio"

# 抓取与平台命令
souwen fetch https://example.com
souwen youtube trending
souwen bilibili search "编程"
souwen wayback cdx https://example.com

# 管理
souwen sources --available-only          # 仅列出静态 gate 与当前 runtime 均可用的数据源
souwen sources --json                    # 输出与 /api/v1/sources 一致的 Source Catalog
souwen serve                             # 启动 API 服务 (默认 :8000)
souwen doctor                            # 静态检查（默认 live=false，不联网）
souwen mcp                               # MCP server info
```

### Python 库

```python
import asyncio
from souwen import search_papers, search_patents

async def main():
    # 便捷入口
    resp = await search_papers("quantum computing", per_page=5)
    for r in resp[0].results:
        print(r.title, "—", r.doi)

    # 应用 API
    from souwen.search import search, search_all
    from souwen.web.fetch import fetch_content
    from souwen.web.wayback import WaybackClient

    # 按 domain + capability 派发
    papers = await search("transformer", domain="paper", limit=5)
    articles = await search("AI news", domain="web", capability="search_news")
    results = await search_all("quantum", domains=["paper", "web", "knowledge"])

    # 抓取
    resp = await fetch_content(["https://example.com"], providers=["builtin"])

    # Wayback 归档
    async with WaybackClient() as wayback:
        snapshots = await wayback.query_snapshots("https://example.com")

asyncio.run(main())
```

### API Server

```bash
SOUWEN_ADMIN_PASSWORD=adminpass souwen serve --host 0.0.0.0 --port 8000
```

主要端点：

```bash
curl "http://localhost:8000/api/v1/search/paper?q=transformer&per_page=5"
curl "http://localhost:8000/api/v1/search/web?q=python"
curl "http://localhost:8000/api/v1/fetch" \
  -H "Authorization: Bearer adminpass" \
  -H "Content-Type: application/json" \
  -d '{"urls":["https://example.com"]}'
curl "http://localhost:8000/api/v1/wayback/cdx?url=https://example.com"
curl "http://localhost:8000/api/v1/sources"
```

`/api/v1/fetch`、`/api/v1/links` 和 `/api/v1/sitemap` 属于管理端抓取能力，需要 Admin Bearer Token；搜索和 `/api/v1/sources` 可再通过 `SOUWEN_USER_PASSWORD` 单独保护。

访问 `/docs` 查看完整 OpenAPI 文档；访问 `/panel#/` 进入 Web UI（默认 souwen-google 皮肤）。`/` 在默认配置下重定向到 `/docs`。

## ⚙️ 配置

配置优先级：env > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > 默认值。

运行 `souwen config init` 会在当前目录生成 `./souwen.yaml` 模板；需要全局配置时，可将模板复制到 `~/.config/souwen/config.yaml`。

## 🏗 架构

三层分离：**展示层（CLI / Server / Panel / Integrations）→ 应用入口（`souwen.search` / `souwen.web.fetch` / `souwen.web.wayback`）→ 注册表层（registry）+ 真实 Client 模块 + 平台层（core）**。

详见 [docs/architecture.md](docs/architecture.md)。

```
src/souwen/
├── core/              平台层：http_client / scraper / rate_limiter / retry / ...
├── registry/          单一事实源：adapter / sources / loader / views
├── paper/             论文客户端
├── patent/            8 个专利客户端
├── web/               搜索、社交、视频、知识、办公、抓取和归档相关客户端
├── cli/ (子包)        CLI 命令（按 domain 组织）
└── server/            FastAPI 应用
```

## 🧩 插件系统

SouWen 支持通过外部 Python 包扩展数据源和 fetch provider。插件通过 setuptools
`entry_points` 或 `souwen.yaml` 的 `plugins` 字段接入，无需修改 SouWen 主仓代码。

提供三种等价的运维入口管理插件：

- **Web Panel** — `/plugins` 路由：图形化列表、启用/禁用、健康检查、安装/卸载
- **CLI** — `souwen plugins list/info/enable/disable/health/reload/install/uninstall/new`
- **HTTP API** — `/api/v1/admin/plugins/*`，详见 [docs/api-reference.md](docs/api-reference.md)

> 安装/卸载默认关闭，需要服务端显式设置 `SOUWEN_ENABLE_PLUGIN_INSTALL=1` 才允许。

文档：

- 对接规范（插件作者）：[docs/plugin-integration-spec.md](docs/plugin-integration-spec.md)
- 运维使用指南：[docs/plugin-management.md](docs/plugin-management.md)

## 🚢 部署

**Docker**（推荐）：

```bash
docker build -t souwen .
docker run -p 8000:49265 \
  -e SOUWEN_ADMIN_PASSWORD=your-admin-password \
  -e SOUWEN_USER_PASSWORD=your-user-password \
  -v ~/.config/souwen:/app/data \
  souwen
```

**HuggingFace Spaces**：参见 `cloud/hfs/` 与 [docs/hf-space-cd.md](docs/hf-space-cd.md)。
**ModelScope**：参见 `cloud/modelscope/`。

**WARP 代理嵌入**（可选，绕过国内网络）：见 `docs/warp-solutions.md` 的五种模式方案对比和 `docs/anti-scraping.md` 的反爬策略。支持运行时通过 Web 面板一键安装 WARP 组件。

## 📚 文档

- [docs/README.md](docs/README.md) — 技术文档入口与阅读导航
- [docs/getting-started.md](docs/getting-started.md) — 快速开始
- [docs/concepts.md](docs/concepts.md) — 核心概念
- [docs/python-api.md](docs/python-api.md) — Python API
- [docs/source-catalog.md](docs/source-catalog.md) — Source Catalog 契约
- [docs/architecture.md](docs/architecture.md) — 架构概览
- [docs/data-sources.md](docs/data-sources.md) — 完整数据源指南与清单（由 registry 自动生成）
- [docs/configuration.md](docs/configuration.md) — 配置层级 / WARP / HTTP backend
- [docs/api-reference.md](docs/api-reference.md) — REST API 参考
- [docs/hf-space-cd.md](docs/hf-space-cd.md) — Hugging Face Space CD / 本地预检 / 部署后验收
- [docs/deployment.md](docs/deployment.md) — 部署
- [docs/anti-scraping.md](docs/anti-scraping.md) — TLS 指纹 / WARP / 限流
- [docs/appearance.md](docs/appearance.md) — 多皮肤前端
- [docs/adding-a-source.md](docs/adding-a-source.md) — 新增数据源指南
- [docs/plugin-integration-spec.md](docs/plugin-integration-spec.md) — 外部插件对接规范
- [docs/plugin-management.md](docs/plugin-management.md) — 插件管理（Web Panel / CLI / API）
- [docs/contributing.md](docs/contributing.md) — 开发者指南
- [docs/internal/rc-readiness-gates.md](docs/internal/rc-readiness-gates.md) — v2.0.0rc1 固定门禁与 evidence manifest 契约
- [docs/internal/](docs/internal/) — 维护者 ADR、分支策略和发布前基线
- [CHANGELOG.md](CHANGELOG.md) — 版本变更

## 🤝 贡献

- 新增数据源：参考 [docs/adding-a-source.md](docs/adding-a-source.md)（`registry/sources/` 加一条 `_reg(...)` 即可）
- 开发外部插件：参考 [docs/plugin-integration-spec.md](docs/plugin-integration-spec.md)
- 代码风格：`ruff format && ruff check`
- 测试：`pytest tests/`

## 📄 License

[GPLv3](LICENSE) · 仅供学习研究用途
