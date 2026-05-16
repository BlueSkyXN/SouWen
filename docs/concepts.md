# 核心概念

本文解释 SouWen 当前对外暴露的核心概念，帮助使用者在 CLI、Python API、
REST API 和 Panel 之间建立同一套理解。

## Domain

`domain` 描述业务领域。当前公开 domain 包括：

| Domain | 含义 |
|---|---|
| `paper` | 学术论文、预印本和开放学术索引 |
| `patent` | 专利检索和专利详情 |
| `web` | 通用网页搜索、SERP、AI 搜索和商业聚合搜索 |
| `social` | 社交平台和社区内容 |
| `video` | 视频搜索、热门视频、详情和字幕 |
| `knowledge` | 百科和知识库 |
| `developer` | 代码托管、技术问答和开发者内容 |
| `cn_tech` | 中文技术社区 |
| `office` | 企业协同和办公搜索 |
| `archive` | 网页归档查询和快照保存 |
| `fetch` | 内容抓取和正文抽取 |

## Capability

`capability` 描述一个源能执行的动作，例如 `search`、`search_news`、
`fetch`、`archive_lookup`。同一个源可以有多个 capability，调用侧通过
`domain + capability` 选择合适的源。

## Source Catalog

Source Catalog 是 SouWen 的公开数据源目录。它由 `SourceAdapter` registry
自动投影，驱动：

- `souwen sources` CLI；
- `/api/v1/sources`；
- Web Panel 数据源页；
- doctor 和管理端配置状态；
- `docs/data-sources.md` 生成文档。

公开 payload 使用 `sources[]` 列表。每个条目包含 `name`、`domain`、
`category`、`capabilities`、`credentials_satisfied`、`configured_credentials`
和 `available` 等字段。调用方应按这些字段过滤，不应假设固定分组字段。

## SourceAdapter

`SourceAdapter` 是一个数据源的声明式契约，记录源的名称、domain、集成方式、
Client 懒加载路径、capability 到方法的映射、认证要求、风险等级、分发范围和
catalog 分类。

新增内置源时，通常只需要：

1. 实现真实 Client；
2. 在 `src/souwen/registry/sources/` 的对应 segment 模块添加 `_reg(SourceAdapter(...))`；
3. 若需要凭据，在 `SouWenConfig` 增加字段并在 adapter 中引用。

## Channel Config

`sources.<name>` 是按源覆盖的运行时频道配置，可控制 `enabled`、`proxy`、
`http_backend`、`base_url`、`api_key`、`headers` 和 `params`。频道配置用于
部署和运行时调优，不改变 Source Catalog 的事实来源。
