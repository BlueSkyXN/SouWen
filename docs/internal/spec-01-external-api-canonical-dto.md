# SPEC-01：External API 与 Canonical DTO

**状态**：Accepted target contract；Phase 1 canonical baseline（非当前运行时声明）

**范围**：External Data API、其 Canonical DTO、错误/安全/可观测性和契约发布规则

**架构来源**：approved HLD v0.4 §11、§20、§21、§25–27，以及已批准的
`Q-004`–`Q-008`、`API-Q-001`、`REL-Q-001` decision register entries

**相关 ADR**：[ADR 0005（HLD register：ADR-04）](adr/0005-breaking-api-release-cutover.md)

## 1. 目的、边界与术语

本 SPEC 定义 `2.0.0` 目标产品的稳定 External Data API。它只覆盖三个 Core use case：
Search、LLM Search、Fetch；调用者是 React Panel、`souwen` REST SDK 和第三方客户端。
它不定义 Provider 的内部 SPI、跨源排序算法、LLM evidence/usage 的最低业务阈值、Fetch
质量阈值、Admin Control API 的完整字段或部署性能数值；这些分别由 SPEC-02/03/04/05/07/10
及 NFR SPEC 负责。

本文的 **当前** 是本文取证时仓库 `main` 的实现形状；**目标** 是待开发的 canonical
contract。除“当前行为映射”外，所有带有“目标”的规则均不得被描述为已实现。

### 已批准的 Phase 1 决策与冻结载体

下列决策已由 owner 批准并成为 target contract；它们不证明 current runtime 已实现任何 target
route、DTO 或 policy。machine-readable 载体是
[`target_api_contract_v2.json`](../../tests/contracts/fixtures/target_api_contract_v2.json)、
[`target_openapi_skeleton_v2.json`](../../tests/contracts/fixtures/target_openapi_skeleton_v2.json) 和
[`target_provider_manifest_v2.json`](../../tests/contracts/fixtures/target_provider_manifest_v2.json)。
它们由 [`test_target_canonical_contract.py`](../../tests/contracts/test_target_canonical_contract.py)
使用 Python standard library 检查，不能替代未来 target route/integration/client conformance。

| Decision | Accepted target rule | Owning target rules |
|---|---|---|
| Q-004 | `providers` 缺省时，按 YAML 的 domain/capability 有序默认表选择一个 primary；只有显式多 provider 才 fanout。多源以等权 RRF (`k=60`) 合并，同分依 YAML priority、provider-local rank、canonical ID；按 stable domain ID、canonical URL、normalized title+year 依次去重并合并 provenance。任一 provider 成功返回 200/`partial=true` 与 failed-provider 明细；全失败才 canonical error。 | API-004；SPEC-05/PROV-002 |
| Q-005 | `answer` 存在时，每个含外部事实的段落至少引用一个 stable evidence ID；每个 item 至少有一个 evidence。Evidence 至少包含 provider、public URL、title/snippet、retrieved time。`usage` 始终存在，仅接收 provider 实报，未知 token/cost 为 `null`；无可验证 evidence 的 provider result 失败。 | API-005；SPEC-05/PROV-003 |
| Q-006 | Fetch 仅规范化 `text/*`、JSON、XML；拒绝 PDF、image/audio/video、`application/octet-stream`。一次 1–20 targets；单响应解压后 hard cap `10 MiB`；正文默认 `200,000` Unicode code points、可配上限 `1,000,000`，超限 `truncated=true`。空正文失败；1–63 个非空字符为 `quality=low`，可作为 partial item。 | API-006；SPEC-05/PROV-004 |
| Q-007 | Search、LLM Search、Fetch、Provider catalog 默认 fail-closed，均要求 USER+ token；Admin 是独立 permission surface。只有显式 target open/guest config 可开放；`/healthz`、`/readyz` 无认证且无敏感信息。`X-SouWen-Token` 在 proxy scenario 优先于 `Authorization`。 | SEC-001；API-002 |
| Q-008 | 初始 budgets（非 SLA）：Search/Fetch `30s`、LLM Search `90s`、hard max `120s`；API in-flight `32`、provider instance `10`、Browser page slots `2`；health/readiness/provider-catalog p95 `<=100ms`（不含 upstream）；其余 memory/image/cold-start/rate budgets 见 target fixture，变更必须 evidence-backed change control。 | API-008；SPEC-05/OBS-002 |
| API-Q-001 | malformed JSON、schema 和 cross-field client-input violation 均为 HTTP 400 / `ERR-002`；413、415、409 等专用状态保持独立，target 不暴露 FastAPI default 422。 | ERR-002；VAL-001 |
| REL-Q-001 | `2.0.0` canonical probes are `/healthz` and `/readyz`; current `/health` and `/readiness` remain same-handler, same-payload, no-redirect aliases for all 2.x and earliest removal is 3.0. | API-007；API-009 |

| 术语 | 含义 |
|---|---|
| External Data API | 对客户端稳定、版本化的 REST contract；目标路径仍为 `/api/v1`。 |
| Canonical DTO | 不携带 Provider SDK object、Pydantic internals 或 Provider raw response 的 JSON 结构。 |
| Provider reference | 公开、稳定的 provider ID 与能力/来源摘要；不是 credential、base URL 或内部实例。 |
| API major | 独立于 package/marketing version 的整数兼容代际；目标 `api_major=2`。 |
| contract fixture | 同时用于服务端、Python REST SDK 与 TypeScript generated client 的输入/输出/错误 golden JSON。 |

## 2. 事实基线与当前行为映射

### 2.1 取证来源

| 证据 | 当前已验证事实 | 仓库路径 |
|---|---|---|
| App 挂载与异常处理 | FastAPI 把 public router 挂在 `/api/v1`、admin router 挂在 `/api/v1/admin`；`/health`、`/readiness` 在根路径；`ErrorResponse` 为平面 `{error, detail, request_id}`。 | `src/souwen/server/app.py` |
| Current auth | `Authorization: Bearer` 与优先的 `X-SouWen-Token` 均可作为应用凭据；Search 随 `user_password`/`guest_enabled` 配置变化，Fetch 为 Admin。 | `src/souwen/server/auth.py`；`src/souwen/server/routes/search.py`；`src/souwen/server/routes/fetch.py` |
| Current rate limiter | Search limiter 是进程内、按 IP 的滑动窗口，默认 60 requests / 60 seconds；仅在 429 响应中写 `Retry-After` 与 `X-RateLimit-*`。 | `src/souwen/server/limiter.py` |
| Current Search DTO | 多个 GET endpoint 分别返回 paper/book/patent/web 等 DTO；它们的 source 字段和 `results` 类型不一致。 | `src/souwen/server/routes/search.py`；`src/souwen/server/schemas/search.py` |
| Current enriched route | `POST /api/v1/search/web/enriched` 接受显式 source list，返回 typed enriched results、`meta` 与 nullable `usage`；它不是目标 `/llm-search`。 | `src/souwen/server/routes/search.py`；`src/souwen/server/schemas/search.py`；`tests/test_server/test_enriched_search_route.py` |
| Current Fetch DTO | `POST /api/v1/fetch` 接受 1–20 URLs、多 provider 和 `fallback`/`fanout`；响应目前来自 `souwen.models.FetchResponse`。 | `src/souwen/server/routes/fetch.py`；`src/souwen/server/schemas/fetch.py`；`src/souwen/models.py`；`tests/test_server/test_fetch_route.py` |
| OpenAPI / tests | OpenAPI 由 FastAPI runtime 生成，并有 schema/route assertions；仓库未发现 committed OpenAPI document 或 client generator。 | `src/souwen/server/app.py`；`tests/test_server/test_openapi_contract.py`；`tests/test_server/test_api_reference_routes.py` |
| Observability/security | Request middleware 透传或生成 `X-Request-ID`，增加 `X-Response-Time`，全局异常处理会 redaction 并将 `request_id` 放入错误 body。 | `src/souwen/server/middleware.py`；`src/souwen/server/app.py`；`tests/test_server/test_app.py` |

### 2.2 Current → target mapping（不等同于兼容承诺）

| Current endpoint / behavior | 当前契约 | Target mapping | 兼容结论 |
|---|---|---|---|
| `GET /api/v1/search/{paper,book,research-output,patent,web,news,images,videos}` | Query 参数、资源类型与返回 DTO 按 endpoint 各异；默认 source 由 registry 解析。 | `POST /api/v1/search` + `SearchRequest` / `SearchPage`。资源域、source selection、分页和排序显式入 body。 | **Breaking**；无 query-shim 或 silent fallback。SPEC-11 负责最终 migration mapping。 |
| `POST /api/v1/search/web/enriched` | 现有显式 LLM-search source、fetch/budget/synthesis 输入与 enriched response。 | `POST /api/v1/llm-search` + `LLMSearchRequest` / `LLMSearchResult`。保留可证明的 provenance、partial 和 nullable usage 语义。 | **Breaking rename/shape review**；不能把现有字段逐字承诺为 v2 canonical field。 |
| `POST /api/v1/fetch` | Admin auth；`urls`、legacy `provider`、`providers`、`strategy`；聚合 `FetchResponse`。 | `POST /api/v1/fetch` + canonical `FetchRequest` / `FetchResult`。 | 同一路径的 **breaking body/response**；`provider` transition field 不进入 canonical DTO。 |
| `GET /api/v1/sources` | Registry catalog，按 current user auth 规则访问。 | `GET /api/v1/providers` + `ProviderCapability`。 | **Breaking rename/shape**；不是 admin config readback。 |
| `/health`、`/readiness` | 根路径，无 auth；包含 runtime version/source SHA。 | `/healthz`、`/readyz` 是 2.0 canonical probes。 | **Accepted REL-Q-001**：old paths remain same-handler, same-payload, no-redirect aliases throughout 2.x; earliest removal is 3.0. |
| `POST /api/v1/summarize`、`POST /api/v1/fetch/summarize` | 当前 LLM route，独立 limiter，依赖 `llm.enabled`。 | 不属于三个目标 Core use case。 | HLD §20 指定退出主产品；迁移与删除证据归 SPEC-11。 |

## 3. Slice routing 与稳定 ID

| Source / requirement | Slice | IDs | 优先级 | 阻塞开发 |
|---|---|---|---:|---:|
| HLD §11 External Data API 与 canonical DTO | API SPEC | API-001–API-010 | P0 | 是 |
| HLD §11.5 Error Contract | API + Security | ERR-001–ERR-012；SEC-001–SEC-003 | P0 | 是 |
| HLD §21 Phase 1 fixtures/OpenAPI/JSON Schema | API + Observability | API-006；OBS-001–OBS-004；VAL-001–VAL-011 | P0 | 是 |
| HLD §20/§27 Q-004–Q-008 | Search/LLM/Fetch/NFR target rules | API-004–API-008；SPEC-05 references | P0 | 已批准；implementation slices must conform |
| HLD §20/§27 Q-011 | Release | REL-001；ADR-04 | P0 | 是 |

以下 ID 是本文件的稳定规则标识。未来文字澄清不得重用或改号；删除规则必须标注
superseded 并保留 traceability。

跨文档引用必须使用全限定形式 `SPEC-01/<ID>`（例如 `SPEC-01/SEC-001`）；本文内的
`SEC-001`、`OBS-001`、`VAL-001` 等是该 namespace 内的简写，不与其他 SPEC 的同名局部
ID 合并。

## 4. Target API envelope、versioning 与 headers

### API-001：Target version boundary

- **Method/path**：目标 External Data API 使用 `/api/v1`；本次 `2.0.0` 是该路径的原位
  breaking cutover，而不是新增 `/api/v2` path。
- **API major**：每一条 target success response、error response 和 OpenAPI `info` extension
  必须声明 `api_major: 2`。HTTP header 使用 `X-SouWen-API-Major: 2`。
- **Package version**：`souwen` package 版本（当前为 `2.0.0rc1`）与 `api_major` 不可互相推导；
  client 必须检查后者。
- **Compatibility rule**：客户端的 supported major 与 server `X-SouWen-API-Major` 不相等时，
  必须在发送业务请求前失败，错误为 `ERR-007 api_major_mismatch`；不得尝试旧 DTO、降级解析或
  猜测 server feature。
- **OpenAPI**：目标 OpenAPI document 是 API contract source artifact（例如 release asset 中的
  `openapi.json`），包含 `info.version`、`x-souwen-api-major: 2` 和 canonical schema。当前
  runtime generated `/openapi.json` 不是已冻结的 target artifact。

### API-002：Common request / response headers

| Header | Direction | Target rule |
|---|---|---|
| `Authorization: Bearer <token>` | request | 默认 application credential channel。 |
| `X-SouWen-Token: <token>` | request | 仅为 upstream proxy 占用 `Authorization` 的部署保留；两者同时存在时该 header 优先，显式错误值不得 fallback。 |
| `Content-Type: application/json` | request | 三个 POST operation 必需；非 JSON body 返回 `ERR-002`。 |
| `Accept: application/json` | request | 推荐；目标 API 只承诺 JSON representation。 |
| `X-Request-ID` | request/response | 可由 client 提供；只接受实现已验证的安全格式/长度，server 生成或回显最终 ID。 |
| `X-Response-Time` | response | 目标继续提供耗时字符串；精确 format/采样由 OBS SPEC 冻结。 |
| `X-SouWen-API-Major` | response | 必须为 ASCII decimal `2`。 |
| `X-RateLimit-Limit`、`X-RateLimit-Remaining`、`X-RateLimit-Reset`、`Retry-After` | response | 适用时必须一致提供；429 必须含 `Retry-After`。 |

### SEC-001：Authentication and authorization

- **Accepted Q-007**：Data API defaults fail-closed. Search、LLM Search、Fetch 和 Provider catalog
  require a USER+ token. Only an explicit target open/guest configuration may open a Data API surface; lack of
  a password never opens it implicitly. `/healthz` and `/readyz` are unauthenticated and non-sensitive.
- 无论 Q-007 的结果，Admin Control API 与 External Data API 必须是不同 permission surface；
  External DTO 不得返回 secret、credential reference、raw provider config、internal base URL 或
  管理操作结果。
- `SOUWEN_ADMIN_OPEN=1` 仅是 current Admin 无密码显式开关，不能成为 target Data API 的
  authorization shortcut。

### SEC-002：Request safety

- Fetch target 必须继承并由 SPEC-04 验证 SSRF、redirect、robots 与 content policy；canonical
  `FetchRequest` 不得成为绕过这些保护的 raw transport wrapper。
- Server-controlled error、log、provenance、config readback 和 diagnostic fields 必须执行
  redaction，不能泄漏 token、cookie、credential-bearing URL、内部 file path、Provider raw
  sensitive body 或 stack trace。Canonical retrieved content 不能因出现通用词 `token` 而被任意
  改写，但服务端不得把请求 credential、Provider secret field 或 raw sensitive metadata 混入内容。

## 5. Canonical DTO rules

### API-003：Common types

| Type | Fields / constraints | Canonical rule |
|---|---|---|
| `RequestContext` | `request_id`, `api_major`, optional `trace_id` | 每个 target response 的 `context`；`request_id` 与 response header 相同。 |
| `ProviderRef` | `id`, `kind`, optional `display_name` | `id` 是 stable public ID，不接受 model ID、URL 或 secret reference。 |
| `ProviderCapability` | `provider`, `capabilities`, `availability`, `provenance` | 脱敏 capability catalog；不得包含 credential/config value。 |
| `ProviderProvenance` | `provider`, optional `attempt`, `outcome`, optional `retrieved_at` | 表示某结果从哪个公开 provider 得到，而非 provider raw payload。 |
| `PageInfo` | `limit`, `next_cursor`, optional `total` | cursor 只是不透明 continuation token；禁止 client 构造语义。 |
| `UsageMetadata` | nullable measured token/cost fields、optional `currency` | unknown 必须为 `null`，不可由估算或 visible call count 推导 billing。 |

### API-004：Search contract

**Operation**：`POST /api/v1/search`

**Actor**：`souwen` REST SDK、React Panel、approved third-party client

**Authentication**：Accepted Q-007 requires USER+ token by default; it does not inherit any current GET
endpoint's implicit default.
**Authorization**：获得 Data API Search capability；禁止读取 Admin config。

`SearchRequest`：

| Field | Type | Required | Validation / semantics |
|---|---|---:|---|
| `query` | string | 是 | 去首尾空格后非空；最大长度需与 SPEC-02 确认，不能静默沿用 current GET 的 `500`。 |
| `domains` | array of enum | 是 | Search resource domains；可选集合与 first provider slice 对齐，扩大必须 additive。 |
| `providers` | `ProviderRef[]` or absent | 否 | absence selects exactly one YAML domain/capability ordered-default primary. Only explicit multiple providers fan out; merge/dedup/partial behavior follows accepted Q-004. |
| `page` | `{limit, cursor?}` | 否 | limit bounds / cursor lifecycle 由 SPEC-02 冻结。 |
| `filters` | object | 否 | 仅允许 schema-listed filters；未知 key 必须 `ERR-002 invalid_request`。 |
| `request_context` | client correlation subset | 否 | client 不得指定 server `api_major` 或 authorization state。 |

`SearchItem`：`id`、`title`、`url`（若领域适用）、`snippet`（若可用）、`rank`、`provenance`；
具体领域 metadata 必须进入明确定义的 `attributes` schema 或 discriminated type，不能回到
current `list[dict]` 的无约束响应。

`SearchPage`：`items: SearchItem[]`、`page: PageInfo`、`meta`（requested/succeeded/failed provider
outcomes）和 `context: RequestContext`。Accepted Q-004 requires equal-weight RRF (`k=60`) for explicit
multi-provider merge; ties use YAML priority, provider-local rank, then canonical ID. Deduplicate by stable
domain ID, canonical URL, then normalized title+year, retaining merged provenance. Any provider success is
HTTP 200 with `meta.partial=true` and machine-readable failures; all-provider failure is ERR-009/ERR-010.

### API-005：LLM Search contract

**Operation**：`POST /api/v1/llm-search`
**Purpose**：一次 LLM/API search operation 的结果、evidence、usage 规范化；它不是任意 model
proxy、agent workflow 或 raw prompt passthrough。

`LLMSearchRequest` 至少包含：

| Field | Type | Required | Validation / semantics |
|---|---|---:|---|
| `query` | string | 是 | canonical normalized query。 |
| `providers` | `ProviderRef[]` | 是 | public registered concrete LLM-search provider ID；禁止 scheme/model/base URL。 |
| `strategy` | enum | 是 | `single`/fanout/first-success 的最终允许集合与 semantics 由 SPEC-03；不接受隐式 Provider selection。 |
| `max_results_per_provider` | integer | 否 | bounded；最终边界由 SPEC-03。 |
| `fetch` | optional bounded object | 否 | 可请求后续安全 Fetch，但不允许关闭 SSRF/content policy。 |
| `budget` | optional bounded object | 否 | timeout/attempt bounds 是执行预算，非 billing guarantee。 |
| `synthesis_profile` | optional opaque profile ID | 否 | 仅 server allowlist，不接受模型或 credential 指定。 |

`LLMSearchResult` 必须包含：`query`、`items: SearchItem[]`、`evidence: EvidenceItem[]`、可选
`answer`、`meta`、`usage: UsageMetadata`、`context`。`EvidenceItem` 至少有 stable `id`、关联
`item_id`、公开 `provenance` 和可显示摘要；answer citation 只可引用 evidence/item ID，不能以
未验证外部 URL 代替 citation。Accepted Q-005 requires every returned item to have evidence. If `answer`
exists, every paragraph containing external facts cites at least one stable evidence ID. Evidence includes
provider, public URL, title/snippet and retrieved time. `usage` always exists and accepts only
provider-reported values; unknown token/cost is `null`. A provider result without verifiable evidence fails;
evidence/items without an answer may be partial success.

### API-006：Fetch contract

**Operation**：`POST /api/v1/fetch`
**Authentication / authorization**：Accepted Q-007 requires USER+ token by default; current Admin-only is
migration evidence, not the target default.
**Idempotency**：纯读取语义；不接收 `Idempotency-Key`。Provider call 仍可能产生配额或费用，
官方 client 默认不得在 dispatch 后自动重放；只有 error `retryable=true`、原 deadline 未过期且
调用方接受潜在重复成本时才可显式 retry。

`FetchRequest`：

| Field | Type | Required | Validation / semantics |
|---|---|---:|---|
| `targets` | array of URL target | 是 | 非空、有上限；最终 count/URL/scheme rule 由 SPEC-04。 |
| `providers` | `ProviderRef[]` or absent | 否 | absence 使用 approved default；不得暴露 current legacy single `provider` field。 |
| `strategy` | enum | 否 | `fallback`/`fanout` 仅作为 current evidence；canonical final set 和 cardinality 由 SPEC-04。 |
| `content` | bounded extraction options | 否 | selector/range/content limit 需 schema-listed；不能返回 raw HTML 或无上限正文。 |
| `policy` | bounded policy options | 否 | robots / content-type choices 必须不能弱化 server security policy。 |

`FetchResult` 必须按 target 返回：`target`、`final_url`、`status`、optional `title`、normalized
`content`、`content_metadata`、`provenance`、optional item-level `error`。`ContentMetadata` 至少包括
media type、charset（若可知）、retrieval timestamp、truncated/length indicators。成功与失败必须能
在同一 batch 中表达；禁止以一个 provider summary 替代每个结果的 provenance。当前 `provider`
transition field 已由 [ADR 0001](adr/0001-public-api-surface.md) 标记为 RC transition，不能进入
target DTO。Accepted Q-006 permits only normalized `text/*`, JSON and XML; it rejects PDF, image/audio/video
and `application/octet-stream`. A request has 1–20 targets, each decompressed response has a `10 MiB` hard cap,
normalized content defaults to `200,000` Unicode code points with a configurable maximum `1,000,000`, and
overflow is `truncated=true`. Empty content fails. A 1–63-character non-empty result is `quality=low` and may
remain as a partial item when no better fallback exists.

### API-007：Provider catalog

**Operation**：`GET /api/v1/providers`

**Response**：`{items: ProviderCapability[], context: RequestContext}`。
**Security**：只返回公开 capability、availability 和已脱敏 provenance；不得泄露 API key、token、
cookie、secret env name/value、private endpoint 或 admin-only diagnostic。
**Compatibility**：不是 current `/api/v1/sources` 的 alias；旧 endpoint 的 transition 是
SPEC-11 的责任。

## 6. Error, retry and HTTP contract

### ERR-001：Target `ErrorResponse`

所有 target 4xx/5xx（包括 request validation）使用：

```json
{
  "error": {
    "code": "provider_timeout",
    "message": "Provider request exceeded its execution budget",
    "retryable": true,
    "request_id": "01HV...",
    "provider": "openalex"
  },
  "context": {
    "request_id": "01HV...",
    "api_major": 2
  }
}
```

`provider` 为 optional public `ProviderRef.id`；它不能承载 raw upstream error。此 envelope 与
current flat `ErrorResponse` **不兼容**，当前格式仍由 `src/souwen/server/schemas/common.py` 定义。

| ID / code | HTTP | Condition | Retryable | Required handling |
|---|---:|---|---:|---|
| ERR-002 `invalid_request` | 400 | syntactically valid JSON but invalid contract combination / unknown request member | no | client fixes input；server logs field/code, not sensitive value. |
| ERR-003 `unauthenticated` | 401 | absent/invalid application credential | no | `WWW-Authenticate: Bearer`; redact token. |
| ERR-004 `forbidden` | 403 | authenticated but missing capability / edition/policy denial | no | no role/config leak. |
| ERR-005 `not_found` | 404 | stable public resource/provider reference not found where endpoint exposes it | no | do not use for hidden Admin resource. |
| ERR-006 `conflict` | 409 | enabled/availability state conflicts with requested operation | conditional | no implicit state mutation. |
| ERR-007 `api_major_mismatch` | 409 | client/server supported API major differs | no | include safe expected/received major; SDK fails before business call when possible. |
| ERR-008 `rate_limited` | 429 | applicable quota exceeded | yes, after `Retry-After` | headers mandatory; scope and limiter design recorded in response metadata only when safe. |
| ERR-009 `provider_timeout` | 504 | provider/operation execution budget elapsed | yes | distinguish deadline from provider-unavailable. |
| ERR-010 `provider_unavailable` | 502 | selected provider(s) unavailable/invalid response after safe mapping | conditional | retain any valid partial success in success envelope when contract allows. |
| ERR-011 `policy_blocked` | 403 | SSRF, redirect, robots or content policy denies Fetch | no | never disclose protected network detail. |
| ERR-012 `internal_error` | 500 | unhandled server failure | no | public message generic; full error only in secured logs. |

### VAL-001：Validation semantics

- Empty-after-trim strings, duplicate IDs where uniqueness is required, unknown enum values, unsupported
  strategy combinations and cross-field budget violations fail before Provider execution.
- **Accepted API-Q-001**: malformed JSON, schema and cross-field client-input violations use `ERR-002` /
  HTTP 400. 413, 415 and 409 retain their specialist statuses; target implementations must not expose FastAPI
  default 422 as canonical contract. Current runtime 422 remains current-only evidence.
- A partial provider result is a 2xx only when `meta.partial=true` and every omitted/failing provider outcome
  is machine-readable. An all-provider failure uses ERR-009 or ERR-010, never an empty successful page.

## 7. Rate limiting, observability and privacy

### API-008 / SEC-003：Rate limit policy

Current 60/60 per-IP in-memory limiter is verified implementation evidence, not target proof. Accepted Q-008
freezes initial non-SLA budgets: Search/Fetch default dispatch deadlines `30s`, LLM Search `90s`, hard maximum
`120s`; API total in-flight `32`; ordinary provider instances `10`; Browser Worker page slots `2`; and default
rate limit `60/min` per credential (IP only when no credential exists). Health/readiness/provider-catalog p95
is `<=100ms` excluding upstream work. Remaining memory/image/cold-start budget values are frozen in the target
fixture and require evidence-backed change control rather than silent gate relaxation.

### OBS-001：Request correlation

Every target operation writes/returns `request_id` and carries the same value in `X-Request-ID`, success
`RequestContext`, error `ErrorResponse`, structured access log and trace (if enabled). Request IDs are
correlation data, not credentials.

### OBS-002：Operation events

For Search/LLM Search/Fetch, emit structured event fields: `operation`, `api_major`, `request_id`, selected
public provider IDs, outcome, partial flag, status, elapsed time, rate-limit decision and canonical error code.
Never emit query/body content, authorization header/token, cookie, secret reference, raw Provider response or
unredacted URL credentials by default.

### OBS-003：Metrics

Required dimensions are operation and result class. Candidate metrics: request count, latency, provider attempt
outcome, partial-result rate, canonical error count and rate-limit rejection count. Cardinality rules, retention,
dashboard/alert threshold and sampling are NFR/Observability SPEC work; no performance target is implied here.

### OBS-004：Audit boundary

Data API read operations create correlation/audit events without storing retrieved content by default. Admin
state/config mutation audit is out of scope and belongs to SPEC-07.

## 8. OpenAPI, generated clients and compatibility

### API-009：Contract publication and generated clients

1. Build the target OpenAPI document from the target canonical schemas and publish it as a versioned, immutable
   release artifact; do not hand-edit generated JSON.
2. `openapi.json` must expose only External Data API / approved health readiness operations, canonical DTOs,
   every documented non-2xx `ErrorResponse`, `x-souwen-api-major: 2`, and operation IDs stable across patch
   releases.
3. Generate the default Python REST SDK distributed as `souwen` and the TypeScript client from that same
   immutable document. Generated clients may be wrapped for ergonomic API only if wrapper behavior cannot widen
   the wire contract.
4. Generated clients must embed their supported `api_major`, inspect `X-SouWen-API-Major` / document extension,
   and raise `api_major_mismatch` before DTO decode when unequal. This is the anti-misconnection rule required
   by ADR-04.
5. CI must diff the generated OpenAPI against an approved baseline, regenerate both clients, run fixture-based
   conformance and reject an unversioned breaking schema/operation/error change.

The Phase 1 checked-in OpenAPI skeleton is a language-neutral, target-only acceptance baseline, not a generated
release artifact and not current runtime `/openapi.json`. It already includes accepted `/healthz` and `/readyz`
and their 2.x aliases so a future generator cannot silently choose a different probe migration policy.

### API-010：Compatibility policy

- Within API major 2, additions may be made only as optional fields, optional operations or documented additive
  enum values with generated-client compatibility tests. Required field removal/rename, type narrowing, changed
  error semantic, changed authentication default, pagination semantic change and provider ID reinterpretation
  require a new API major decision.
- No target client may detect an unknown server major and silently parse `dict`/`any`, retry under an old path or
  downgrade a security rule.
- The original `/api/v1` path does not make current v2 RC payloads stable forever. ADR-04 accepts the cutover;
  SPEC-11 owns external usage evidence, release notes, replacement mapping and residue audit.
- Current OpenAPI is generated live when `expose_docs=true`; `expose_docs=false` disables `/docs` and
  `/openapi.json`. Target release artifact generation must not depend solely on an exposed production docs URL.

## 9. Acceptance criteria and validation evidence

| VAL ID | Acceptance criterion | Required evidence |
|---|---|---|
| VAL-002 | Current / target mapping lists every target operation and does not call target paths current. | Review against `src/souwen/server/routes/*.py` and this document. |
| VAL-003 | Target OpenAPI exposes exactly the canonical Search, LLM Search, Fetch, Providers and approved probe operations with `api_major=2`. | OpenAPI snapshot/semantic diff test. |
| VAL-004 | Search, LLM Search and Fetch request validation exercises blank/oversize/duplicate/invalid strategy/cross-field cases before Provider call. | Deterministic route/contract tests. |
| VAL-005 | Every target error code has a status, retryability, redaction and JSON envelope test. | Contract fixture tests including 400/401/403/409/429/502/504/500. |
| VAL-006 | 401 carries `WWW-Authenticate`; 429 carries all four rate-limit headers; request ID correlation is identical in header/body/log event. | Integration tests. |
| VAL-007 | No success/error fixture contains a credential, raw Provider payload, Pydantic/private field, internal path or unredacted sensitive URL. | Negative fixture/redaction tests. |
| VAL-008 | Generated Python and TypeScript clients are generated from the same immutable OpenAPI artifact and pass all golden fixtures. | CI generation diff + client conformance jobs. |
| VAL-009 | Client/server API-major mismatch stops before DTO decode or business retry and returns a diagnosable safe error. | Client/server compatibility test matrix. |
| VAL-010 | Partial result semantics preserve valid items and enumerate failed providers; all-provider failure is a canonical error. | Multi-provider deterministic fixtures. |
| VAL-011 | Fetch SSRF/redirect/policy denial remains enforced through target DTO and maps to `policy_blocked` without sensitive disclosure. | SPEC-04 security integration tests. |

## 10. Open questions and required owner confirmation

| ID | Decision required | Owner / closure artifact | Implementation constraint until closed |
|---|---|---|---|
| Q-004 | Multi-provider default selection, ordering, deduplication and partial-success ranking. | Search owner; SPEC-02. | No default ordering or implicit fanout in `SearchRequest`. |
| Q-005 | LLM evidence and usage minimum, citation completeness and partial policy. | LLM Search / Provider owners; SPEC-03/05. | Keep evidence/usage fields explicit; do not synthesize cost. |
| Q-006 | Fetch content type, length and quality thresholds. | Fetch owner; SPEC-04. | No arbitrary max/content acceptance rule promoted to product contract. |
| Q-007 | External Data API default auth policy and public/guest boundaries. | Security/product owner; SPEC-07. | Do not inherit current route-by-route auth implicitly. |
| Q-008 | Performance, concurrency, memory, image and cold-start targets; target limiter scope. | NFR owner; NFR SPEC. | No quota/SLA claim. |
| API-Q-001 | Whether target input violations use HTTP 400 or preserve HTTP 422. | API owner; this SPEC revision. | Must be decided consistently before generated clients. |
| REL-Q-001 | Whether `/health`/`/readiness` are retained in parallel during cutover or only `/healthz`/`/readyz` ship. | Release/operations owner; SPEC-10. | Do not remove probes based on this document alone. |

## 11. Handoff boundaries

- **SPEC-02** owns `SearchRequest.filters`, page cursor, default provider strategy, aggregation, rank and
  deduplication; it must only emit `SearchPage` / `SearchItem` defined here.
- **SPEC-03** owns `LLMSearchRequest` strategy, evidence minimum, answer/citation semantics and `UsageMetadata`
  population; null remains the only representation for unknown usage/cost.
- **SPEC-04** owns Fetch URL/content policy, SSRF/redirect behavior, maximums and `ContentMetadata` values.
- **SPEC-05** owns Provider IDs/capability validation and provider-to-canonical-error mapping.
- **SPEC-07** owns final Data/Admin permission model and secret readback protection.
- **SPEC-10** owns health/readiness rollout, OpenAPI release artifact publication and operational rollout.
- **SPEC-11** owns legacy CLI/MCP/Python imports/current routes migration communications and removal evidence.
