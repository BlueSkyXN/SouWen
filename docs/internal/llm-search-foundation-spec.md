# LLM Search Foundation SPEC

状态：Implementation baseline
范围：`TASK-001`、`TASK-002`
基线：`78635c7e9ae53967b6e834459b77941c58ad45ee`

## 1. 目标与边界

本 SPEC 只建立 LLM Search 的配置、身份、可用性、超时、单次请求和共享 deadline
基础，不注册任何 UniAPI source，不调用外部 API，也不新增公开 REST、CLI、MCP 或 Panel
入口。

未来 Citation API 必须是 additive 的 `POST /api/v1/search/web/enriched`。当前
`GET /api/v1/search/web` 的请求、响应、认证、限流和错误语义保持不变。

本单元明确不做：

- Ark/OpenAI/Anthropic/Qwen/Gemini wire adapter 或 fixture parser；
- `SearchCandidate`、enrichment、fetch、summary、answer；
- 动态 model、任意 base URL 或 API Key 的公开请求参数；
- UniAPI source declaration、catalog 数量变化或默认 fan-out；
- live/付费 smoke、binary、container、package 或 Panel build。

## 2. 配置合同

共享 gateway 使用唯一配置面：

```yaml
llm_search_gateways:
  uniapi:
    api_key: <secret>
    base_url: https://gateway.example.com/v1
```

环境变量使用 JSON 对象：

```text
SOUWEN_LLM_SEARCH_GATEWAYS={"uniapi":{"api_key":"...","base_url":"https://gateway.example.com/v1"}}
```

具体 source 的安全 override 继续使用现有 channel：

```yaml
sources:
  <concrete_source_id>:
    enabled: false
    api_key: <optional-source-secret>
    base_url: https://source-override.example.com/v1
    timeout: 45
    params: {}
```

每个字段独立按以下优先级解析：

```text
sources.<source_id>.api_key/base_url
→ llm_search_gateways.<gateway_id>.api_key/base_url
→ concrete source 明确声明的 legacy fallback（当前不存在）
```

规则：

- `api_key` 与 `base_url` 必须都存在，source 才满足 gateway configuration。
- 空字符串按未配置处理；`base_url` 必须是带 hostname 的 HTTP(S) URL。
- `SourceChannelConfig.timeout` 是可选 override，范围 `1..300` 秒。
- `params` 只能承载 tool knobs；`model`、`model_id`、`scheme_id`、`source_id`、
  `gateway_id` 属于 immutable identity，出现即拒绝。
- config model 与 resolved runtime object 的 `repr` 不得包含 API Key 或 private base URL。
- Doctor/catalog/admin 只报告缺失路径，例如
  `llm_search_gateways.uniapi.api_key`，不返回配置值。

## 3. Scheme 与 concrete source 合同

`SearchSchemeSpec` 至少包含：

```text
scheme_id
gateway_id
upstream_channel
protocol
endpoint_kind
tool_schema
candidate_contract
default_timeout_seconds
source_grade
request_builder / response_parser implementation hooks
```

`ConcreteSearchSourceSpec` 至少包含：

```text
source_id
scheme_id
exact model_id
stability
default_enabled
optional timeout_seconds
last_verified_at
```

不变量：

1. `scheme_id`、`gateway_id` 和 `source_id` 使用稳定的小写 snake-case；不兼容 scheme
   变更通过新的 `_vN` ID 表达。
2. 一个 `source_id` 只能映射一个 `(scheme_id, model_id)` tuple。
3. 同一 tuple 只能有一个 `source_id`，不得通过别名绕过验证或计费策略。
4. `model_id` 原样保存，不 slugify、不在运行时通过 `params` 覆盖。
5. concrete source 必须引用已注册 scheme；只有同时具备 request builder 与 parser 的
   source-grade scheme 才能实例化可执行 source。
6. `experimental` source 必须 `default_enabled=false`，投影时同时设置
   `runtime_default_enabled=false`，且不得声明 `default_for`。现有 source 的
   `default_enabled` 继续只表示 UI 默认，不改变其历史 runtime 行为。
7. Scheme registry 是内部 implementation registry；公开 source inventory 仍只来自
   `SourceAdapter`/Source Catalog。Projection factory 是两者之间的唯一桥接。

Projection 后的 gateway requirement 使用以下稳定路径：

```text
llm_search_gateways.<gateway_id>.api_key
llm_search_gateways.<gateway_id>.base_url
```

现有 `credential_fields`、flat config、self-hosted source 和 external plugin 的解析保持兼容。

## 4. Timeout、retry 与 deadline

### 4.1 Source timeout

- 普通 web source 未声明 method timeout 时，继续使用全局 timeout，并受现有 `15s` cap。
- LLM Search scheme 可声明独立 default，例如 Ark `45s`；source channel 可在 `1..300s`
  内 override。
- 聚合 timeout、scheme/source timeout 与 HTTP socket timeout 是三个不同层级，不合并成
  一个语义不明字段。
- `web_search()` 根据 selected adapter 的 `MethodSpec` 解析 timeout，不允许 source-name
  `if/else`。

### 4.2 Single attempt

- `SouWenHttpClient` 默认 request policy 保持现有网络错误重试合同。
- 可计费 request 必须显式选择 `single_attempt`；timeout/connect error 只发送一次。
- `llm_complete()` 默认 retry 保持兼容；foundation 提供独立的内部 single-attempt dispatch，
  供后续 search/synthesis orchestration 显式使用。
- HTTP status、auth、rate limit 与 project exception mapping 保持现有语义。

### 4.3 Shared deadline

- Endpoint/search stage 创建一次 monotonic deadline。
- 每个 provider attempt 只能取得 `min(requested_timeout, remaining_budget)`。
- 后续 `first_success` source 复用同一个 deadline，不得重新开始完整预算。
- remaining budget 为 0 时，在发送请求前 fail closed。

## 5. Compatibility 与安全

- Public API：无新增 route，无旧 schema 变化。
- Admin API：`SourceChannelConfigResponse`/update request additive 增加可选 `timeout`；
  source/catalog 状态 additive 返回 value-free `missing_credential_fields`、`config_valid` 与
  `config_reason`。
- Config API：additive 增加 `llm_search_gateways`，`/admin/config` 继续递归脱敏 `api_key`。
- Python API：新 contract 放在 `souwen.web.llm_search`；`souwen` package root 不导入它，
  避免启动或 optional dependency 回归。
- Registry：不注册任何 concrete source，因此本 PR 不改变 source catalog 数量。
- Tests：全部使用 fixture/mock，不读真实 HOME，不访问网络或凭据。

## 6. Validation Plan

| ID | 验证目标 | 证据 |
|---|---|---|
| `FND-VAL-001` | scheme/source ID 与 tuple 双向唯一 | registry unit tests |
| `FND-VAL-002` | source → shared gateway 逐字段优先级 | config/contract unit tests |
| `FND-VAL-003` | 缺 key/base URL 的安全诊断一致 | config + registry meta tests |
| `FND-VAL-004` | identity params 与 experimental default 不能被覆盖 | contract unit tests |
| `FND-VAL-005` | 普通 source 仍受 15s cap，声明型 source 可使用 45s/override | web search tests |
| `FND-VAL-006` | HTTP/LLM single-attempt 只调用一次 | core/LLM mocked tests |
| `FND-VAL-007` | 默认 HTTP/LLM retry 不回归 | core/LLM mocked tests |
| `FND-VAL-008` | shared deadline 不被第二个 attempt 重置 | monotonic fake-clock tests |
| `FND-VAL-009` | admin timeout schema/update 与 config redaction | server/OpenAPI tests |
| `FND-VAL-010` | 现有 registry/docs/plugin/import surface 不漂移 | registry/docs/import checks |

本地只执行 deterministic tests 与 lint，不执行 binary/container/package/Panel build：

```bash
pytest tests/test_config.py tests/test_config_loader.py tests/test_doctor.py -q --tb=short
pytest tests/registry/test_consistency.py tests/registry/test_catalog.py -q --tb=short
pytest tests/test_web/test_llm_search_registry.py tests/test_web/test_search.py -q --tb=short
pytest tests/test_http_client.py tests/test_llm/test_client.py -q --tb=short
pytest tests/test_server/test_app.py tests/test_server/test_openapi_contract.py -q --tb=short
ruff check <changed Python files>
ruff format --check <changed Python files>
python3 tools/gen_docs.py --check
python3 scripts/ci/check_no_legacy_terms.py
git diff --check
```

完整 matrix、package、binary 与 container 由 PR 的 GitHub Actions 负责。本单元不发起新的
release-candidate workflow。

## 7. 轻量 RTM

| Requirement / blocker | Implementation unit | Validation |
|---|---|---|
| `REQ-005` provenance identity | Scheme/source specs + immutable tuple registry | `FND-VAL-001`, `FND-VAL-004` |
| `REQ-007` Registry 单一事实源 | spec-to-`SourceAdapter` projection | `FND-VAL-001`, `FND-VAL-010` |
| `REQ-010` 不泄露 | hidden repr + dotted missing-field diagnostics + redaction | `FND-VAL-003`, `FND-VAL-009` |
| `REQ-013` concrete identity 不可变 | duplicate/alias/model override rejection | `FND-VAL-001`, `FND-VAL-004` |
| `BLOCK-001` shared gateway availability | `llm_search_gateways` + source override resolver | `FND-VAL-002`, `FND-VAL-003` |
| `REQ-008` / `BLOCK-002` timeout budget | method/source timeout + monotonic deadline | `FND-VAL-005`, `FND-VAL-008` |
| `REQ-009` / `BLOCK-003` 重复计费 | explicit HTTP/LLM single-attempt path | `FND-VAL-006`, `FND-VAL-007` |
| `REQ-006` 旧 API 兼容 | no route/schema mutation outside additive admin timeout | `FND-VAL-009`, `FND-VAL-010` |

## 8. Rollback

本单元无 migration、无 source registration、无 live deployment。回滚可按模块独立进行：

1. 移除未被 source 使用的 `llm_search_gateways` 和 `souwen.web.llm_search` contract；
2. 移除 additive source timeout，普通 web timeout 自动回到原 15 秒实现；
3. 移除 opt-in single-attempt 路径，默认 HTTP/LLM retry 从未改变；
4. 旧 `GET /api/v1/search/web` 无需数据或客户端迁移。
