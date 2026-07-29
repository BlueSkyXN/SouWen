# TypeScript SDK

SouWen Panel 使用由冻结 OpenAPI artifact 生成的 TypeScript client。唯一契约输入是
`contracts/openapi/souwen-openapi-2.0.0rc4.json`；生成物位于
`panel/src/core/sdk/index.ts`，不得手工编辑。

## 生成与验证

```bash
PYTHONPATH=src python3 tools/gen_typescript_sdk.py --write
PYTHONPATH=src python3 tools/gen_typescript_sdk.py --check
PYTHONPATH=src pytest tests/test_typescript_sdk_generator.py -v --tb=short
cd panel && npm test -- --run src/core/sdk/index.test.ts
```

Generator 固定记录 `SDK_VERSION`、`SUPPORTED_API_MAJOR`、由 OpenAPI enum 派生的
`SEARCH_DOMAINS` 和 canonical artifact 的
SHA-256，并对 35 个 DTO、8 个 operation、security/header contract、schema ref、重复
operation/schema 和不能安全映射的 schema shape 进行 fail-closed 校验。`--check` 只比较
生成结果，不写文件。

## 使用

```ts
import { SouWenClient, type SearchRequest } from '@core/sdk'

const client = new SouWenClient({
  baseUrl: '', // 同源 Panel；远程 host 必须进入构建期 allow-list
  token: sessionToken,
})

const request: SearchRequest = {
  query: 'quantum computing',
  domains: ['paper'],
}

const page = await client.search(request)
```

公开方法覆盖：

- `search()`、`llmSearch()`、`fetch()`、`listProviders()`；
- `healthz()`、`readyz()` 及 OpenAPI 保留的 `health` / `readiness` aliases。

第一条业务请求发送前，client 通过 `/healthz` 校验 API major 2 和 target rollout。每个
响应在 DTO 使用前校验 `X-SouWen-API-Major`、`X-SouWen-Rollout-Mode`、
`X-Request-ID` 与 payload `context` correlation。SDK 不自动 retry，避免重放可能消耗
配额或费用的 LLM Search / Fetch 请求。

## 认证与浏览器边界

默认认证通道是 `Authorization: Bearer`。只有显式设置
`authChannel: 'x-souwen-token'` 时才发送 `X-SouWen-Token`。Private HFS edge 占用
`Authorization` 时，programmatic client 可把 edge token 作为 `edgeToken`，并以
`authChannel: 'x-souwen-token'` 将 application token 放入 `X-SouWen-Token`；两个通道不会静默
fallback。

这不改变 embedded Panel 的浏览器认证边界：Panel 只支持同源 private-edge browser
session/cookie 或普通单一 Bearer application token。Panel 不读取 cookie，不采集、组合或持久化
dual-token；需要 edge token 与 application token 同时存在的 flow 仅供 programmatic SDK caller
显式构造，不是 Panel 登录模型。

这个 TypeScript client 是 Panel/Vite 构建面的一部分，不是独立 npm package。空字符串表示
同源 API；绝对 `baseUrl` 必须是无 userinfo/query/fragment 的 HTTP(S) URL，并满足同源、
loopback 或 `VITE_ALLOWED_API_HOSTS` allow-list。Panel 不应把 token、error payload 或配置中的
secret 值写入 URL、日志、DOM、snapshot 或 bundle。

Canonical 非成功响应抛出 `SouWenAPIError`；API major 不一致、contract correlation 失败和
transport/timeout 分别使用独立错误类型。调用方可以读取结构化状态、request ID、
`Retry-After` 和 rate-limit metadata，但 retry 策略必须由调用方显式决定。
