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

先读取 catalog，再为 Search、LLM Search 和 Fetch 选择 `availability=available` 且声明对应
capability 的 Provider。不要在客户端维护平行 Provider 清单。

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
    "providers": [{"id": "openalex", "kind": "search"}],
    "page": {"limit": 3}
  }'
```

响应是 `SearchPage`：`items` 为 canonical results，`page` 提供 limit/cursor，`meta` 和
`context` 提供本次执行与请求信息。调用方应保留每条结果的 provenance。

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

响应是 `LLMSearchResult`，包含 `answer`、`evidence`、`items` 和始终存在的 `usage` 对象。
`usage` 只反映 Provider 回报，未知值为 `null`，不能推导平台账单。

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
