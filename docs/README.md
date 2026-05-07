# SouWen 技术文档

这里是 SouWen 主仓库的技术文档入口。`docs/` 里的内容跟代码一起进入 PR、
review 和测试，适合记录快速开始、API、配置、架构、数据源事实、插件规范和
部署验收规则。

GitHub Wiki 可以承载场景化手册；仓库内技术事实仍以本目录为准。本轮不重写 Wiki。

## 文档边界

| 区域 | 定位 |
|---|---|
| Public docs | 面向使用者和插件作者，描述当前正式架构、API、配置、部署和扩展方式 |
| Internal docs | 面向维护者，记录分支策略、ADR、baseline、历史决策和发布前检查 |

Public docs 不要求读者理解历史路径；需要保留背景材料时，放入 `docs/internal/`。

## 入门与概念

| 文档 | 用途 |
|---|---|
| [getting-started.md](./getting-started.md) | 安装、CLI、Python、API Server 的最短路径 |
| [concepts.md](./concepts.md) | domain、capability、Source Catalog、频道配置等核心概念 |
| [python-api.md](./python-api.md) | 推荐 Python API 入口与示例 |

## 数据源与配置

| 文档 | 用途 |
|---|---|
| [source-catalog.md](./source-catalog.md) | `/api/v1/sources`、CLI JSON 和 Panel 共用的公开 Source Catalog 契约 |
| [data-sources.md](./data-sources.md) | 数据源指南与完整清单，由 registry 自动生成 |
| [configuration.md](./configuration.md) | 配置优先级、`SouWenConfig` 字段、频道级 `sources.<name>` 覆盖 |

## API 与集成

| 文档 | 用途 |
|---|---|
| [api-reference.md](./api-reference.md) | Python API、CLI、REST API、MCP 工具和服务端端点 |
| [anti-scraping.md](./anti-scraping.md) | TLS 指纹、代理、WARP、SSRF 防护和爬虫限制 |
| [warp-solutions.md](./warp-solutions.md) | WARP 五种模式和部署选择 |

## 架构与开发

| 文档 | 用途 |
|---|---|
| [architecture.md](./architecture.md) | 展示层、应用入口、registry、真实 client 模块和 core 平台层 |
| [adding-a-source.md](./adding-a-source.md) | 在主仓新增数据源的实现、注册、配置和测试流程 |
| [contributing.md](./contributing.md) | 开发环境、测试、前端构建、提交规范和 PR 流程 |

## 插件系统

| 文档 | 用途 |
|---|---|
| [plugin-integration-spec.md](./plugin-integration-spec.md) | 外部插件接入契约：SourceAdapter、fetch handler、配置和测试 |
| [plugin-management.md](./plugin-management.md) | Web Panel、CLI、HTTP API 的插件管理和排障 |

## 部署与前端

| 文档 | 用途 |
|---|---|
| [deployment.md](./deployment.md) | Docker、本地服务、部署后回读和运行时保护 |
| [hf-space-cd.md](./hf-space-cd.md) | Hugging Face Space CD、本地门禁和部署后验收 |
| [appearance.md](./appearance.md) | Web Panel 多皮肤、主题、构建方式和前端架构 |

## Internal docs

| 文档 | 用途 |
|---|---|
| [internal/development-branching.md](./internal/development-branching.md) | `v2-dev` 长期集成线、staged PR 和发布前 gate 边界 |
| [internal/testing-playbook.md](./internal/testing-playbook.md) | 外部能力测试收口 playbook |
| [internal/zero-key-benchmark.md](./internal/zero-key-benchmark.md) | 无 API Key 场景的时间点实测报告 |
| [internal/adr/0001-public-api-surface.md](./internal/adr/0001-public-api-surface.md) | public API surface 决策 |
| [internal/adr/0002-versioning-policy.md](./internal/adr/0002-versioning-policy.md) | 公开版本号决策规则 |

## 与 GitHub Wiki 的边界

- `docs/` 是技术事实源：适合写字段定义、API shape、配置优先级、架构、生成规则和测试约束。
- Wiki 是场景化手册：适合写数据源怎么选、API Key 怎么配、自建源怎么理解和常见问题。
- Wiki 不维护完整数据源表，也不复制完整 API reference；需要细节时链接回本目录。

Wiki 入口位于：

```text
https://github.com/BlueSkyXN/SouWen/wiki
```
