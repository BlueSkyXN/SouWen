# SouWen 架构概览

SouWen 2.0 是 target-only information-retrieval API。公开产品能力只有 Search、LLM Search
和 Fetch；HTTP contract 由 frozen OpenAPI 固定，Python/TypeScript 调用方只使用生成 SDK。

<!-- BEGIN AUTO: REGISTRY SUMMARY -->
**Provider v2 摘要**：Manifest Registry 从内置 package 发现 **104** 份 manifest、**110** 个 adapter。

Provider Manager 对 manifest、configuration、secret reference 和显式 factory 做 preflight，并按需构造 provider；旧 source registry 不参与启动、路由或文档生成。
<!-- END AUTO: REGISTRY SUMMARY -->

## 1. 分层与依赖方向

```text
Panel / generated Python SDK / generated TypeScript SDK
                         │
                         ▼
delivery/api ── frozen OpenAPI、auth/rate-limit、canonical DTO
                         │
                         ▼
modules/search | modules/llm_search | modules/fetch
                         │
                         ▼
platform/provider_manager + platform/provider_spi
                         │
                         ▼
providers/*/manifest.py + spec.py + adapter.py
                         │
                         ▼
providers/runtime_clients + common_runtime
```

- `delivery/api/` 是唯一公开 Data API 边界；Server host 只额外挂载 Panel、`whoami` 和只读
  Admin config/doctor/ping。
- `modules/` 只编排 canonical request、Provider selection、deadline 与 canonical result。
- `platform/manifest_registry/` 校验静态 manifest，`ProviderManager` 负责 preflight、按需构造、
  probe 和生命周期关闭。
- `providers/runtime_clients/` 是私有传输/解析实现，不属于 Python 公共 API。
- `common_runtime/` 提供 transport、SSRF/security、retry/resilience、observability 和共享
  Provider support；它不能依赖 delivery、modules 或具体 Provider。

依赖门禁由 `scripts/ci/check_architecture_dependencies.py` 执行。Provider package 不能维护第二份
catalog，也不能绕过 `ProviderManager` 直接进入公开路由。

## 2. Provider v2 单一事实源

每个内置 Provider package 以 `manifest.py` 声明：

- package ID、版本与 `provider-v2` contract；
- `search`、`llm_search`、`fetch` 中的一个或多个 capability；
- adapter ID/export 与 availability；
- non-secret configuration schema 与 secret reference；
- 受审 egress、proxy/browser 要求、risk 与 observability dimensions。

`src/souwen/providers/catalog.py` 只发现三个内置 namespace 下的 `manifest.py`，不会为生成文档
而导入 adapter 或 runtime client。`ManifestRegistry` 拒绝重复 package/adapter；Server、Provider
catalog 与生成文档都消费同一组 manifests。

Provider spec 负责把 deployment config/secret 映射成受审 factory 输入。运行时 factory 只在
Provider 被选择时构造私有 client，所有 client 由 `ProviderManager.close_all()` 统一关闭。

<!-- BEGIN AUTO: CROSS-DOMAIN FETCH SOURCES -->
以下 package 通过独立 adapter 提供多个公开能力：

| Provider package | Capabilities | Adapter IDs |
|---|---|---|
| `exa` | `search`, `fetch` | `exa-search`, `exa-fetch` |
| `firecrawl` | `search`, `fetch` | `firecrawl-search`, `firecrawl-fetch` |
| `kimi_code` | `search`, `fetch` | `kimi_code-search`, `kimi_code-fetch` |
| `metaso` | `search`, `fetch` | `metaso-search`, `metaso-fetch` |
| `tavily` | `search`, `fetch` | `tavily-search`, `tavily-fetch` |
| `xcrawl` | `search`, `fetch` | `xcrawl-search`, `xcrawl-fetch` |
<!-- END AUTO: CROSS-DOMAIN FETCH SOURCES -->

## 3. 公开 HTTP 与 SDK contract

Frozen OpenAPI 只有 8 个 paths：

| Method | Path | Responsibility |
|---|---|---|
| POST | `/api/v1/search` | 多 domain Provider Search |
| POST | `/api/v1/llm-search` | model-bound LLM Search |
| POST | `/api/v1/fetch` | 逐目标 Fetch 与 SSRF-safe result |
| GET | `/api/v1/providers` | 安全的 Provider catalog 投影 |
| GET | `/healthz`, `/health` | canonical health 与 retained alias |
| GET | `/readyz`, `/readiness` | canonical readiness 与 retained alias |

`tools/gen_openapi.py` 生成 immutable artifact；`tools/gen_client_sdk.py` 与
`tools/gen_typescript_sdk.py` 从该 artifact 生成 client/DTO。手写 route、Panel transport 或并行 DTO
不能扩展 Data API。

Host-only `GET /api/v1/whoami`、Admin config/doctor/ping 和 `/panel` 不进入 frozen target OpenAPI。
Admin API 始终受 Admin auth 保护，且只读、脱敏、不执行 live Provider probe。

## 4. Search、LLM Search 与 Fetch

### Search

`SearchModuleService` 使用 domain default selection 或调用方的显式 ProviderRef；每个 selection
映射到 manifest adapter ID。单 Provider 失败转换为 canonical `ProviderError`，不会回退到已删除
的 facade/registry 聚合器。

### LLM Search

LLM Search Provider 绑定 exact model/scheme/gateway identity。部署方在
`llm_search_gateways` 配置 private base URL/API key，并在 `sources` 中显式启用一个内置 LLM
Search Provider。正式 HFS promotion 会要求该能力可用并执行 live call。

### Fetch

`FetchModuleService` 只调用 manifest 声明的 Fetch adapter。目标 URL 在交给直连 client、第三方
提取服务或 Browser Worker 前执行 canonical SSRF 校验；redirect 逐跳重新绑定并校验。Browser
Worker 只监听受认证的内部 loopback，不是外部 API。

## 5. 配置、认证与部署

配置优先级为 environment > `./souwen.yaml` > user config > `.env` > defaults。Provider secret
只能通过部署配置解析，不进入 manifest、catalog、Admin response、日志或生成文档。

User credential 保护四个 Data API 操作；Admin credential 保护 host-only Admin 投影。无密码 Admin
仅在显式 `SOUWEN_ADMIN_OPEN=1` 的本地/CI 场景开放，正式 HFS 必须为 `admin_open=false`，并验证
anonymous Admin 被拒绝。

HFS wrapper 固定 exact Git source SHA，并分别校验 wrapper SHA、runtime source SHA、Browser Worker
source SHA、config revision、Panel、OpenAPI、Search/LLM Search/Fetch live 与 restart 后状态。

## 6. 新增 Provider

新增 Provider 的最小闭环是：

1. 在对应 `providers/{information_sources,fetch_sources,llm_sources}/<id>/` 增加
   `manifest.py`、`spec.py`、`adapter.py`；需要私有 transport/parser 时使用
   `providers/runtime_clients/` 与 Common Runtime。
2. 增加 manifest/spec/adapter parity、eligibility、factory lifecycle、dispatch 和 normalization 的
   deterministic tests。
3. 运行 Provider、architecture、OpenAPI/SDK、生成文档与 residue gates。

完整步骤见 [添加 Provider](adding-a-source.md)。

## 7. 验证护栏

- `pytest tests/ -q --tb=short`
- `python scripts/ci/run_profile.py --profile sdk-contract --profile server-contract --profile provider-runtime`
- `python scripts/ci/check_architecture_dependencies.py`
- `python scripts/ci/check_no_legacy_terms.py`
- `python tools/gen_openapi.py --check`
- `python tools/gen_client_sdk.py --check`
- `python tools/gen_typescript_sdk.py --check`
- `python tools/gen_docs.py --check`
- `cd panel && npm test && npm run build:local && npm run check:artifact`
