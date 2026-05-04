# SouWen 搜文

**[English](README.en.md)** | 中文

> 面向 AI Agent 的**统一搜索库**：学术论文 + 专利 + 网页 + 社交 + 视频 + 百科 + 开发者社区 + 中文技术 + 企业办公 + 档案 + 内容抓取

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.1.1-orange)](CHANGELOG.md)

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

SouWen（搜文）为 AI Agent 提供统一的多源搜索接口，**所有数据源通过 `SourceAdapter` 单一事实源声明**，归一化为 Pydantic v2 数据模型。

注册表架构使源的新增成本降到 **1-2 处**改动；CLI / API / 前端均按 10 个 domain 组织。

### 特性

- **94 个内置异构数据源**（由 `registry` 统一派生，外部插件运行时追加）：
  - `paper` 19 源 · `patent` 8 源 · `web` 29 源（engines/api/self_hosted）
  - `social` 5 源 · `video` 2 源 · `knowledge` 1 源
  - `developer` 2 源 · `cn_tech` 9 源 · `office` 1 源 · `archive` 1 源
  - `fetch` 横切能力：17 个抓取提供者 + 5 个跨域提供者
- **统一 Pydantic v2 数据模型**：`PaperResult` / `PatentResult` / `WebSearchResult` / `FetchResult` / `WaybackCDXResponse` / ...
- **异步优先**：httpx + asyncio，per-loop Semaphore 控制并发
- **智能限流**：Token Bucket + 滑动窗口，每源独立
- **curl_cffi TLS 指纹**：15+ 爬虫类源用浏览器指纹伪装过盾
- **WARP 五模式代理**：wireproxy / kernel / usque / warp-cli / external，支持运行时动态安装和管理
- **MCP 协议**：供 Claude Code / Cursor / Windsurf 等 AI 助手直接调用
- **多皮肤 Web UI**：souwen-google（默认）/ souwen-nebula / carbon / apple / ios（SCSS Modules + Zustand）

## 📦 安装

```bash
# 核心：Python 库 + CLI
pip install souwen

# API 服务（FastAPI）+ TLS 指纹 + 网页搜索
pip install "souwen[server,tls,web,scraper]"

# 全量（含 PDF / Crawl4AI / Scrapling / newspaper 等）
pip install "souwen[server,tls,web,scraper,pdf,crawl4ai,scrapling,newspaper,readability,robots,mcp]"
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
souwen sources                          # 列出所有数据源
souwen serve                             # 启动 API 服务 (默认 :8000)
souwen doctor                            # 健康检查
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

    # facade API（推荐）
    from souwen.facade import search, search_all, fetch_content, archive_lookup

    # 按 domain + capability 派发
    papers = await search("transformer", domain="paper", limit=5)
    articles = await search("AI news", domain="web", capability="search_news")
    results = await search_all("quantum", domains=["paper", "web", "knowledge"])

    # 抓取
    resp = await fetch_content(["https://example.com"], provider="builtin")

    # Wayback 归档
    snapshots = await archive_lookup("https://example.com")

asyncio.run(main())
```

### API Server

```bash
souwen serve --host 0.0.0.0 --port 8000
```

主要端点：

```bash
# 顶层动词形式
curl "http://localhost:8000/api/v1/search/paper?q=transformer&per_page=5"
curl "http://localhost:8000/api/v1/search/web?q=python"
curl "http://localhost:8000/api/v1/fetch" -X POST -d '{"urls":["https://example.com"]}'

# Domain 形式（规划中，后端路由拆分后上线）
curl "http://localhost:8000/api/v1/paper/search?q=transformer"
curl "http://localhost:8000/api/v1/archive/cdx?url=https://example.com"
```

访问 `/docs` 查看完整 OpenAPI 文档；访问 `/panel#/` 进入 Web UI（默认 souwen-google 皮肤）。`/` 在默认配置下重定向到 `/docs`。

## ⚙️ 配置

配置优先级：env > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > 默认值。

首次运行 `souwen config init` 会在 `~/.config/souwen/config.yaml` 生成模板。

## 🏗 架构

三层分离：**展示层（CLI / Server / Panel / Integrations）→ 门面层（facade/）→ 注册表层（registry/）+ 业务层（paper/patent/...）+ 平台层（core/）**。

详见 [docs/architecture.md](docs/architecture.md)。

```
src/souwen/
├── core/              平台层：http_client / scraper / rate_limiter / retry / ...
├── registry/          单一事实源：adapter / sources / loader / views
├── facade/            门面层：search / fetch / archive / aggregate
├── paper/             19 个论文客户端
├── patent/            8 个专利客户端
├── web/               30 个网页相关（engines / api / self_hosted）
├── social/ video/ knowledge/ developer/ cn_tech/ office/ archive/ fetch/
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
docker run -p 8000:8000 \
  -e SOUWEN_API_PASSWORD=your-password \
  -v ~/.config/souwen:/app/data \
  souwen
```

**HuggingFace Spaces**：参见 `cloud/hfs/` 与 [docs/hf-space-cd.md](docs/hf-space-cd.md)。
**ModelScope**：参见 `cloud/modelscope/`。

**WARP 代理嵌入**（可选，绕过国内网络）：见 `docs/warp-solutions.md` 的五种模式方案对比和 `docs/anti-scraping.md` 的反爬策略。支持运行时通过 Web 面板一键安装 WARP 组件。

## 📚 文档

- [docs/README.md](docs/README.md) — 技术文档入口与阅读导航
- [docs/architecture.md](docs/architecture.md) — 架构概览
- [docs/data-sources.md](docs/data-sources.md) — 完整数据源指南与清单（由 registry 自动生成）
- [docs/configuration.md](docs/configuration.md) — 配置层级 / WARP / HTTP backend
- [docs/api-reference.md](docs/api-reference.md) — REST API 参考
- [docs/hf-space-cd.md](docs/hf-space-cd.md) — Hugging Face Space CD / 本地预检 / 部署后验收
- [docs/anti-scraping.md](docs/anti-scraping.md) — TLS 指纹 / WARP / 限流
- [docs/appearance.md](docs/appearance.md) — 多皮肤前端
- [docs/adding-a-source.md](docs/adding-a-source.md) — 新增数据源指南
- [docs/plugin-integration-spec.md](docs/plugin-integration-spec.md) — 外部插件对接规范
- [docs/plugin-management.md](docs/plugin-management.md) — 插件管理（Web Panel / CLI / API）
- [docs/contributing.md](docs/contributing.md) — 开发者指南
- [GitHub Wiki](https://github.com/BlueSkyXN/SouWen/wiki) — 用户手册与场景化导航
- [CHANGELOG.md](CHANGELOG.md) — 版本变更

## 🤝 贡献

- 新增数据源：参考 [docs/adding-a-source.md](docs/adding-a-source.md)（`registry/sources.py` 加一条 `_reg(...)` 即可）
- 开发外部插件：参考 [docs/plugin-integration-spec.md](docs/plugin-integration-spec.md)
- 代码风格：`ruff format && ruff check`
- 测试：`pytest tests/`

## 📄 License

[GPLv3](LICENSE) · 仅供学习研究用途
