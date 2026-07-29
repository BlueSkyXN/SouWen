# API 接口参考

SouWen v2 是 target-only API。canonical contract 有三种查看方式：

- 仓库内 frozen artifact：
  [`contracts/openapi/souwen-openapi-2.0.0rc4.json`](../contracts/openapi/souwen-openapi-2.0.0rc4.json)
- 当前 HFS Swagger：<https://blueskyxn-souwen.hf.space/docs>
- 当前 HFS OpenAPI JSON：<https://blueskyxn-souwen.hf.space/openapi.json>

Frozen artifact 对应 immutable source/version；live URLs 对应当前可变部署。两者版本号相同不代表
source SHA 相同，部署 provenance 应另从 `/healthz`、HF runtime 和 workflow evidence 回读。

## Canonical paths

| Method | Path | Auth |
|---|---|---|
| POST | `/api/v1/search` | User credential |
| POST | `/api/v1/llm-search` | User credential |
| POST | `/api/v1/fetch` | User credential |
| GET | `/api/v1/providers` | User credential |
| GET | `/healthz`、`/readyz` | none |
| GET | `/health`、`/readiness` | none; 2.x aliases |

客户端可用 `Authorization: Bearer`，或在上游占用 `Authorization` 时使用优先级更高的
`X-SouWen-Token`。业务请求应发送 `X-SouWen-API-Major: 2`。响应含 `X-Request-ID`、
`X-SouWen-API-Major` 和固定的 `X-SouWen-Rollout-Mode: target`。

以下示例假设 token 已通过安全方式放入 `SOUWEN_TOKEN`，不要把真实值写入文档、命令历史、
Issue 或截图：

```bash
BASE_URL=https://blueskyxn-souwen.hf.space
AUTH_HEADER="X-SouWen-Token: $SOUWEN_TOKEN"
```

## Providers

先读取 catalog，了解 Search、LLM Search 和 Fetch Provider 的当前 eligibility/availability。
LLM Search 必须显式选择 Provider；Search/Fetch 可以使用 Server default，也可以由 SDK/API
caller 显式选择。不要在客户端维护平行 Provider 清单。

```bash
curl --fail-with-body "$BASE_URL/api/v1/providers" \
  -H "$AUTH_HEADER" \
  -H "X-SouWen-API-Major: 2"
```

`GET /api/v1/providers` 是 `ProviderManifest` catalog、`ManifestRegistry` 和
`ProviderManager` 的安全投影。返回可用性和缺失配置，不返回凭据。

## Search

```bash
curl --fail-with-body "$BASE_URL/api/v1/search" \
  -H "$AUTH_HEADER" \
  -H "X-SouWen-API-Major: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "retrieval augmented generation",
    "domains": ["paper"],
    "page": {"limit": 3}
  }'
```

响应是 `SearchPage`：`items` 为 canonical results，`page` 提供 limit/cursor，`meta` 和
`context` 提供本次执行与请求信息。调用方应保留每条结果的 provenance。`providers` 缺省时，
`search_defaults` 为该 domain 选择一个 primary；当前 `paper` primary 是 `crossref`。显式传入
一个 Provider 时只调用该 Provider；显式传入多个 Provider 时按 Search contract fanout/merge。

## LLM Search

先从 Providers 读取当前 available 的 `llm_search` Provider ID，再替换示例占位符：

```bash
curl --fail-with-body "$BASE_URL/api/v1/llm-search" \
  -H "$AUTH_HEADER" \
  -H "X-SouWen-API-Major: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is retrieval augmented generation?",
    "providers": [{"id": "<available-llm-provider>", "kind": "llm_search"}],
    "strategy": "single",
    "max_results_per_provider": 3
  }'
```

响应是 `LLMSearchResult`，包含 `evidence`、`items`、可空的 `answer` 和始终存在的 `usage`
对象。`answer` 是非必填、nullable 字段：Provider 只返回可验证结构化证据时为 `null`，这仍是有效
成功；只有 Provider 返回可引用的 synthesis 时才有文本回答。`usage` 只反映 Provider 回报，未知值
为 `null`，不能推导平台账单。

## Fetch

```bash
curl --fail-with-body "$BASE_URL/api/v1/fetch" \
  -H "$AUTH_HEADER" \
  -H "X-SouWen-API-Major: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "targets": ["https://example.com/"],
    "providers": [{"id": "builtin-fetch", "kind": "fetch"}],
    "strategy": "fallback",
    "policy": {"respect_robots": true}
  }'
```

Fetch 一次接受 1–20 个 `http/https` target。`respect_robots` 只能保持为 `true`；客户端选项
不能关闭服务端 SSRF、redirect、DNS、robots 或 response-size 保护。每个 `FetchResult` 独立报告
`success`、`failed` 或 `blocked`，以及自己的 provenance 或安全错误。

`strategy=fallback` 按 Provider 顺序逐 target 尝试，获得高质量成功后停止；低质量成功在没有
更好结果时保留为 partial item。`strategy=fanout` 对每个 `target × provider` 组合并发执行，
按 target-major、provider-minor 顺序返回独立 `FetchResult`，不合并不同 Provider 的正文。
Panel 为降低日常操作成本固定发送 `fallback`；SDK/API caller 可以显式请求 `fanout`。完整执行
语义见 [SPEC-04](./internal/spec-04-fetch-module-lld.md)。

IP-pinned builtin Fetch 只广告 `gzip, deflate`，并在 raw stream 上增量解码；解压后正文达到
`10 MiB + 1 byte` 时立即关闭 stream 并返回 `payload_too_large`，不会先完整缓冲压缩响应。

## Admin 与 probes

Admin 仅保留 read-only：

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/admin/config` | 脱敏配置视图 |
| GET | `/api/v1/admin/doctor` | Provider 静态 eligibility 与 availability |
| GET | `/api/v1/admin/ping` | 认证后的轻量存活检查 |
| GET | `/api/v1/whoami` | 当前角色与 feature projection |

Admin endpoints 必须使用 admin credential。没有密码的 admin access 只在服务端显式设置
`SOUWEN_ADMIN_OPEN=1` 时存在，HFS production 不允许开启。

`/healthz` 与 `/readyz` 不代表业务匿名开放。`/readyz` 还要求 Browser Worker、目标配置和
required components ready；部署验收应同时检查 HTTP 200、`rollout_mode=target`、source/wrapper
SHA 与 component 状态。

## 错误与退休接口

验证错误使用 canonical error envelope；调用方应记录 `X-Request-ID`，不要依赖上游原始异常文本。
`401/403` 表示 application auth 不满足，`429` 携带 rate-limit headers，`503` readiness 失败时
不得被当作健康部署。

已退休且不存在 replacement alias 的 public surface 包括 `/sources`、旧 `/search/*`、legacy
`/fetch`、citation/detail/archive-save、recursive crawl、browser-fetch product entry 与旧
enriched-search。优先使用 generated Python/TypeScript SDK，而不是手写旧请求形状。
