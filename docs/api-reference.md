# API 接口参考

SouWen v2 是 target-only API。frozen OpenAPI 公开路径仅为：

| Method | Path | Auth |
|---|---|---|
| POST | `/api/v1/search` | User credential |
| POST | `/api/v1/llm-search` | User credential |
| POST | `/api/v1/fetch` | User credential |
| GET | `/api/v1/providers` | User credential |
| GET | `/healthz`、`/readyz` | none |
| GET | `/health`、`/readiness` | none; 2.x aliases |

客户端可用 `Authorization: Bearer` 或优先的 `X-SouWen-Token`，并应发送
`X-SouWen-API-Major: 2`。响应含 `X-Request-ID`、`X-SouWen-API-Major` 和固定的
`X-SouWen-Rollout-Mode: target`。

`GET /api/v1/providers` 是 `ProviderManifest` catalog、`ManifestRegistry` 和
`ProviderManager` 的安全投影。Admin 仅保留 read-only `GET /api/v1/admin/config`、
`GET /api/v1/admin/doctor`、`GET /api/v1/admin/ping`，仍受 admin auth 保护。

已退休且不存在 replacement alias 的 public surface 包括 `/sources`、旧 `/search/*`、
legacy `/fetch`、citation/detail/archive-save、recursive crawl、browser-fetch product entry 与旧
enriched-search。请使用 generated Python/TypeScript SDK，而非手写旧请求形状。
