# SouWen 技术文档

这里是 SouWen 主仓库的技术文档入口。`docs/` 里的内容跟代码一起进入 PR、review 和测试，适合记录 API、配置、架构、数据源事实、插件规范和部署验收规则。

GitHub Wiki 负责用户手册和阅读导航；权威技术细节仍以本目录为准。

## 数据源与配置

| 文档 | 用途 |
|---|---|
| [data-sources.md](./data-sources.md) | 数据源指南与完整清单，由 registry 自动生成 |
| [configuration.md](./configuration.md) | 配置优先级、`SouWenConfig` 字段、频道级 `sources.<name>` 覆盖 |
| [zero-key-benchmark.md](./zero-key-benchmark.md) | 无 API Key 场景的时间点实测报告 |

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
| [hf-space-cd.md](./hf-space-cd.md) | Hugging Face Space CD、本地门禁和部署后验收 |
| [appearance.md](./appearance.md) | Web Panel 多皮肤、主题、构建方式和前端架构 |

## 与 GitHub Wiki 的边界

- `docs/` 是技术事实源：适合写字段定义、API shape、配置优先级、架构、生成规则和测试约束。
- Wiki 是用户手册：适合写快速开始、数据源怎么选、API Key 怎么配、自建源怎么理解、常见问题和部署路径。
- Wiki 不维护完整数据源表，也不复制完整 API reference；需要细节时链接回本目录。

Wiki 入口初始化后位于：

```text
https://github.com/BlueSkyXN/SouWen/wiki
```
