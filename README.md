# SouWen 搜文

**[English](README.en.md)** | 中文

> 面向 AI Agent 和自动化脚本的 target-only Search、LLM Search 与 Fetch API。

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0rc4-orange)](CHANGELOG.md)

> 当前候选版本为 **Souwen v2rc4**（Python/runtime `2.0.0rc4`）。`v2.0.0rc4` tag、
> GitHub prerelease 与 HFS promotion 只有在 exact-candidate release gates 全部通过后才能创建；
> 已发布的 [`v2.0.0rc3`](https://github.com/BlueSkyXN/SouWen/releases/tag/v2.0.0rc3)
> 保留为上一 immutable baseline，当前发布状态以 GitHub Releases 和 HFS 实时读回为准。
> 这不是 `2.0.0` GA，也尚未发布到 PyPI。

**作者**: [@BlueSkyXN](https://github.com/BlueSkyXN) · **项目地址**: [github.com/BlueSkyXN/SouWen](https://github.com/BlueSkyXN/SouWen) · **协议**: [GPLv3](LICENSE)

> **⚠️ 声明：本项目仅供 Python 学习与技术研究使用。** 涵盖 API 聚合、全栈开发（FastAPI + React）、爬虫技术（TLS 指纹 / 反爬绕过）与异步编程等方向。请勿用于违反法律法规或第三方服务条款的用途。

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

SouWen（搜文）为 AI Agent、Python 集成和服务端应用提供统一的 target-only 数据 API。
公开业务能力只有 **Search、LLM Search 和 Fetch**。Provider 的事实来源是
`ProviderManifest` catalog、`ManifestRegistry` 与 `ProviderManager`；`/api/v1/providers`
是它们的安全投影，不是旧 Source Catalog 的兼容别名。

### 特性

<!-- BEGIN AUTO: SOURCE METRICS -->
- **104 个内置 Provider v2 package**，共 **110 个 capability adapter**。
  - Search：**88** 个 package · LLM Search：**2** 个 · Fetch：**20** 个。
<!-- END AUTO: SOURCE METRICS -->
- **Frozen OpenAPI + generated SDK**：Python root 只暴露 generated sync/async SDK；Panel 使用同一 OpenAPI 生成的 TypeScript SDK
- **统一 canonical DTO**：Search、LLM Search、Fetch、Provider Catalog 和 probes 使用明确的 Pydantic v2 contract
- **安全边界**：target Data API 使用 user credential；Admin 仅提供 read-only config、doctor 与 ping

## 📦 安装

```bash
# 从当前 main 源码线安装核心库
git clone https://github.com/BlueSkyXN/SouWen.git
cd SouWen
pip install -e .

# 默认安装提供 generated Python SDK；运行 Server 再安装 runtime extra
pip install -e ".[server,tls,web,robots,scraper]"
```

## 🚀 快速开始

### Python REST SDK

```python
from souwen import SouWenClient
from souwen.delivery.client_sdk import SearchRequest

with SouWenClient("http://127.0.0.1:8000", token="your-user-token") as client:
    page = client.search(SearchRequest(query="quantum computing", domains=["paper"]))
    for item in page.items:
        print(item.title, item.url)
```

SDK 同时提供 `AsyncSouWenClient`，并在首次业务请求前以 `/healthz` 校验 API major 2。
完整认证、HFS 双 token 和错误处理见 [Python SDK 文档](docs/python-sdk.md)。
Panel 使用同一 OpenAPI artifact 生成的 [TypeScript SDK](docs/typescript-sdk.md)。

### API Server

```bash
SOUWEN_USER_PASSWORD=userpass SOUWEN_ADMIN_PASSWORD=adminpass \
  uvicorn souwen.server.app:app --host 0.0.0.0 --port 8000
```

主要端点：

```bash
curl "http://localhost:8000/api/v1/search" \
  -H "Authorization: Bearer userpass" \
  -H "X-SouWen-API-Major: 2" \
  -H "Content-Type: application/json" \
  -d '{"query":"transformer","domains":["paper"]}'
curl "http://localhost:8000/api/v1/providers" \
  -H "Authorization: Bearer userpass" \
  -H "X-SouWen-API-Major: 2"
```

`POST /api/v1/fetch` 与 Search/LLM Search 同属 target Data API，使用 user credential。
管理面只保留 `GET /api/v1/admin/config`、`GET /api/v1/admin/doctor` 和
`GET /api/v1/admin/ping`。没有 rollout switch、`/sources`、citation/detail/archive-save、
递归抓取、浏览器抓取产品入口或旧 enriched-search public endpoint。

访问 `/docs` 查看完整 OpenAPI 文档；访问 `/panel#/` 进入单一 Calm Precision 管理面。`/` 在默认配置下重定向到 `/docs`。

## ⚙️ 配置

配置优先级：env > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > 默认值。

从 `souwen.example.yaml` 创建项目配置；需要全局配置时，可将其复制到 `~/.config/souwen/config.yaml`。

## 🏗 架构

三层分离：**展示层（Server / Panel）→ generated SDK / Module APIs → ProviderManifest catalog、ManifestRegistry、ProviderManager 和 runtime clients**。

详见 [docs/architecture.md](docs/architecture.md)。

```
src/souwen/
├── delivery/          frozen OpenAPI、generated Python SDK 与 HTTP adapters
├── platform/          ProviderManifest / ManifestRegistry / ProviderManager
├── providers/         provider specs、adapters 与 runtime clients
├── modules/           Search、LLM Search 与 Fetch application services
├── common_runtime/    shared transport、security、resilience 与 observability
└── server/            FastAPI 应用
```

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
根级 [`hfs-dev.toml`](hfs-dev.toml) 是 registry-only 部署登记：记录 source lane、Space ID、
workflow ownership 和当前 Space setting 名称，不保存任何真实凭据值，也不授权通用同步工具
修改远端设置；当前参考 `hf_space_sync.py` 会在读取 `.env` 或联网前拒绝该 manifest。

该登记已按 HFS v2.1 明确分类为 `project_class = "preview"`，canonical Space 的角色是
`target_role = "primary"`。日常 Preview 变更允许通过现有受控 workflow 直接更新 canonical
Space，不要求另建 candidate Space 或先做 promotion；release workflow 中的 `candidate_sha`
仍是不可变源码证据，不代表本项目变成生产环境。任何 Space Secret 都必须先写入 manifest
声明的 Git ignored 本地明文 `.env`，远端 Secret 不能成为唯一事实源。
**ModelScope**：参见 `cloud/modelscope/`。

部署环境可按自身网络策略配置代理；公开 API 不提供 WARP 管理或运行时安装入口。

## 📚 文档

- [docs/README.md](docs/README.md) — 技术文档入口与阅读导航
- [docs/getting-started.md](docs/getting-started.md) — 快速开始
- [docs/concepts.md](docs/concepts.md) — 核心概念
- [docs/python-api.md](docs/python-api.md) — Python API
- [docs/source-catalog.md](docs/source-catalog.md) — Provider Catalog 契约
- [docs/architecture.md](docs/architecture.md) — 架构概览
- [docs/data-sources.md](docs/data-sources.md) — 完整 Provider 指南与清单（由 manifest catalog 自动生成）
- [docs/configuration.md](docs/configuration.md) — 配置层级 / WARP / HTTP backend
- [docs/api-reference.md](docs/api-reference.md) — REST API 参考
- [docs/hf-space-cd.md](docs/hf-space-cd.md) — Hugging Face Space CD / 本地预检 / 部署后验收
- [docs/deployment.md](docs/deployment.md) — 部署
- [docs/anti-scraping.md](docs/anti-scraping.md) — TLS 指纹 / WARP / 限流
- [docs/appearance.md](docs/appearance.md) — Calm Precision 管理面板
- [docs/adding-a-source.md](docs/adding-a-source.md) — 新增数据源指南
- [docs/contributing.md](docs/contributing.md) — 开发者指南
- [docs/internal/rc-readiness-gates.md](docs/internal/rc-readiness-gates.md) — v2.0.0rc4 固定门禁与 evidence manifest 契约
- [docs/internal/](docs/internal/) — 维护者 ADR、分支策略和发布前基线
- [CHANGELOG.md](CHANGELOG.md) — 版本变更

## 🤝 贡献

- 新增 Provider：参考 [docs/adding-a-source.md](docs/adding-a-source.md)（新增 manifest/spec/adapter 与 conformance tests）
- 代码风格：`ruff format && ruff check`
- 测试：`pytest tests/`

## 📄 License

[GPLv3](LICENSE) · 仅供学习研究用途
