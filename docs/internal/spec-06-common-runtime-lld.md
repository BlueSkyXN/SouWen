# SPEC-06：Common Runtime LLD

**Status**: Proposed; incremental Phase 3 implementation baseline

**Date**: 2026-07-24

**Source**: HLD ARCH-006、§8.5、§10、§21 Phase 3；SPEC-08 admission rules

**Implementation baseline**: Phase 2 Draft PR #193, head `65a0641b8ee1a5ad5aceee82c43dfff438cd0b7d`

## 1. 目的与边界

本文定义 Common Runtime 的职责、准入测试、依赖方向、兼容迁移方式和可派生测试。
Phase 3 是同行为搬移，不借迁移改变 HTTP、retry、SSRF、配置、认证、Provider 或产品语义。

Common Runtime 只接收同时满足以下条件的组件：

1. 至少两个真实生产消费者；
2. 单一技术职责，不拥有 Search、LLM Search、Fetch、Provider 或 Delivery 决策；
3. 输入、输出、错误、timeout 和 cancellation 语义明确；
4. 可以在无真实网络、browser、生产 secret 和 HOME 配置的条件下独立测试；
5. 不依赖 `souwen.modules`、`souwen.providers`、Delivery、registry source truth 或具体 Provider。

目录名称不是准入证据。未满足任一条件的实现继续保留在 legacy 路径，直到后续 LLD 修订和
验证工件补齐。

## 2. 责任模型

| Area | 拥有 | 不拥有 |
|---|---|---|
| Transport | 通用 HTTP/TLS/proxy/connection 生命周期；明确的 cancellation/stream contract | SSRF product policy、Provider query、业务 fallback |
| Resilience | timeout budget、retry primitive、backoff、通用 rate/concurrency primitive | Provider header 解析、Search partial success、scraper/CAPTCHA policy |
| Security | 可复用 SSRF target primitive、credential redaction、安全的 redirect building block | Fetch result、Admin permission、Provider credential schema |
| Observability | request context primitive、timing/provenance carrier、runtime source identity | ASGI middleware、process logging policy、Provider/source catalog |
| Configuration | 中立 namespace/revision/secret-reference primitive | `SouWenConfig` 中的 Provider、WARP、Plugin、Server 或产品 defaults |
| Testing | 已稳定 runtime port 的 fake、clock、fault injection 和 conformance harness | 直接修补 legacy registry/fetch global 的 pytest fixture |

## 3. 当前候选准入裁决

| Candidate | Consumers | Decision | Reason / prerequisite |
|---|---|---|---|
| `souwen.provenance` source SHA resolver | `doctor.py`, `server/app.py` | **ACCEPT-01，首切片** | stdlib-only、单一 runtime identity 职责、已有 deterministic tests、无领域依赖 |
| request ID `ContextVar` / getter / logging filter | Server error handling、logging filter | CONDITIONAL-02 | 只迁 context primitive；ASGI middleware、header validation、UUID 与 access log 留在 Delivery |
| DNS-bound SSRF target resolver | `BaseScraper`、Google Patents 与 Fetch callers | CONDITIONAL-03 | 只迁 value object/resolve/validate；不得迁构造 `FetchResult` 的 helpers；先冻结同步 DNS 和 cancellation 限制 |
| generic secret text/URL/payload redaction | CLI、Server、MCP、plugin manager、LLM/fetch errors | CONDITIONAL-04 | 先拆 generic primitive；Pydantic adapter 与 LLM gateway topology policy 不进入 Security primitive |
| `SouWenHttpClient` | OpenAlex、HAL 等 Provider | CONDITIONAL-05 | 先冻结 native cancellation、无 stream v1、trusted auto-redirect 与 config adapter 边界 |
| token/sliding-window limiter | OpenAlex、The Lens 等 Provider | CONDITIONAL-06 | 先补 acquire cancellation/state fixture；Provider 负责把 headers 转成通用数值 |
| `OAuthClient` | EPO OPS、CNIPA | DEFER | 基础 Transport 之后独立决定 Transport/Security owner、token timeout 与 refresh cancellation |
| `core.concurrency` 原 API | Search、Web aggregation | REJECT-AS-IS | `"search"` / `"web"` channel 是领域名称；不能原样成为 runtime API |
| retry presets / `poll_retry` | 当前只有一个 production consumer 或无 consumer | REJECT | 不满足两个消费者；scraper/CAPTCHA exception set 含领域策略且缺独立测试 |
| `BaseScraper` / browser pool / fingerprint | scraper/browser Provider | REJECT | 混合 anti-bot、SSRF、Provider backend、browser optional runtime；不是中立 transport |
| `SessionCache` | 当前仅 Server shutdown lifecycle | REJECT | 单一消费者、持久化 secret/state owner 未决，且 Fetch cache 归属另由 Fetch LLD 决定 |
| 完整 `SouWenConfig` / credential resolution | HTTP、Server、Provider、registry | REJECT | 混合 Provider/Delivery/WARP/Plugin 语义；迁移会制造第二份配置和 source truth |
| `setup_logging()` | CLI、Server bootstrap | REJECT | process-global handler policy 与 side effect 属于 bootstrap/Delivery |
| current pytest global fixtures | registry/fetch/plugin tests | REJECT | 直接依赖 legacy globals，不得进入 production distribution 的 runtime testing API |

## 4. 目标目录与依赖

```text
src/souwen/common_runtime/
  observability/
    __init__.py
    provenance.py
  security/
  transport/
  resilience/
  configuration/
  testing/
```

允许方向：

```text
modules/providers/platform -> common_runtime
common_runtime subpackage -> Python stdlib and explicitly admitted third-party runtime libraries
```

禁止方向：

```text
common_runtime -> modules/providers/delivery/server/registry/concrete client
common_runtime -> legacy core compatibility wrapper
```

Legacy path 可以单向 re-export canonical implementation；canonical implementation 不得反向 import
legacy path。Architecture dependency checker 持续执行 DEP-004 和 `DEP-DYNAMIC`。

## 5. ACCEPT-01：Runtime source provenance

### 5.1 Public internal interface

Canonical path：`souwen.common_runtime.observability`。

```python
SOURCE_SHA_ENV: str
SOURCE_SHA_FILE_ENV: str
SOURCE_SHA_FILENAME: str

def get_source_sha() -> str | None: ...
```

这是 repository-internal architecture contract，不提升为 end-user Python API；`souwen.__init__`
不得新增 export。

### 5.2 输入与优先级

`get_source_sha()` 按以下顺序求值，命中显式来源后不继续 fallback：

1. `SOUWEN_SOURCE_SHA`；
2. `SOUWEN_SOURCE_SHA_FILE` 指定文件；
3. `runtime.source.sha` 的 cwd、PyInstaller bundle root、executable-relative 与 module-relative
   candidates，按现有顺序检查。

合法值是恰好 40 位十六进制 Git SHA；输出统一为 lowercase。空值、格式不合法或候选文件
读取失败返回 `None`。

### 5.3 错误、timeout 与 cancellation

- 仅捕获候选文件读取的 `OSError` 并按现状返回 `None`。
- 不捕获编程错误，不记录文件内容或环境变量值。
- 只有同步本地环境变量和小文件读取；无网络、无 retry、无 timeout 参数、无 cooperative
  cancellation point。
- 显式 env 值不合法时 fail closed 为 `None`，不得继续使用可能过期的文件 fallback。

### 5.4 状态、一致性与副作用

- 每次调用重新读取环境和候选文件，不缓存、不维护 global mutable state。
- 不创建、不修改、不删除 provenance 文件。
- 多线程/多 event loop 调用共享零状态；结果只取决于调用时 process/filesystem 输入。

### 5.5 兼容迁移

1. 将实现移动到 `common_runtime/observability/provenance.py`。
2. `common_runtime/observability/__init__.py` 只 export 四个已声明符号。
3. `souwen.provenance` 保留 compatibility re-export，并保证旧/新符号对象 identity 相同。
4. `doctor.py` 与 `server/app.py` 改为 canonical import，证明至少两个真实消费者已迁移。
5. 不更改环境变量、文件名、搜索顺序、PyInstaller handling 或 error semantics。

Rollback 是让 consumers 恢复 legacy import 并恢复原实现文件；不需要数据迁移。

## 6. 后续条件切片

### 6.1 Request context

Canonical path 为 `souwen.common_runtime.observability`，内部接口为
`request_id_var: ContextVar[str]`、`get_request_id() -> str` 和 `RequestIDFilter`。默认值为
`"-"`；调用方负责以 `ContextVar.set()` 的 token 在 `finally` 中 reset。filter 只给传入的
`LogRecord` 设置当前 `request_id` 并返回 `True`，不验证、生成或记录 ID。

`souwen.server.middleware` 保留 compatibility re-export 和 `RequestIDMiddleware`。ASGI scope、
incoming header validation、UUID generation、response header、timing 和 access log 保留在 Delivery。
该切片无 I/O、timeout、retry 或 cooperative cancellation；ContextVar 由 Python runtime 按 task
隔离。退出证据必须包含旧/新 object identity、task isolation、logging filter 和 Server
error-response correlation parity。

### 6.2 SSRF resolver

Canonical path 为 `souwen.common_runtime.security`，repository-internal interface 为：

```python
@dataclass(frozen=True, slots=True)
class ResolvedFetchTarget:
    original_url: str
    connect_url: str
    host_header: str
    sni_hostname: str | None

def resolve_fetch_target(url: str) -> tuple[ResolvedFetchTarget | None, str]: ...
def validate_fetch_url(url: str) -> tuple[bool, str]: ...
```

Security 只拥有 scheme/userinfo/host/port/IP/DNS validation 和 IP-bound target 描述。输入是单个
URL string；成功时输出保留原 URL、已校验 IP literal `connect_url`、原 authority `Host` 和
HTTPS DNS hostname SNI，失败时输出 `None`/`False` 与现有中文 reason。规则保持 http/https only、
userinfo reject、localhost/private/reserved/legacy numeric IPv4 reject、IDNA lowercase、mixed DNS
fail-closed、去重后 IPv4 preference、fake-IP DNS `198.18.0.0/15` allow，以及 IP literal 无 SNI。

DNS 继续同步调用 `socket.getaddrinfo(host, None, AF_UNSPEC, SOCK_STREAM)`。接口没有 timeout、retry
或 cooperative cancellation 参数；阻塞期间不能由 asyncio task cancellation 中断。调用方拥有外层
budget，但本切片不声称外层 async timeout 能终止正在执行的同步 DNS。迁移不能顺手改为 async DNS、
thread offload、resolver cache 或多 IP retry。

预期解析/验证失败以 `(None, reason)` / `(False, reason)` 返回；只将 `socket.gaierror`、`OSError`、
端口 `ValueError`、IDNA `UnicodeError` 和现有解析分支映射为既有 reason，不新增 logging 或 exception
surface。函数无 cache/global mutable state，不发 HTTP，不记录 URL/hostname，不读取配置或 secret。

`souwen.web.fetch` 必须 object-identical re-export 三个 canonical symbols，使既有 import path 保持可用；
Fetch helpers 继续通过 legacy module global 调用 `validate_fetch_url`，因此现有针对
`souwen.web.fetch.validate_fetch_url` 的 deterministic monkeypatch contract 保留。`BaseScraper` 改用
canonical import，消除 Core → Web reverse edge。local fixture functional harness 必须同时 patch/restore
canonical resolver 与已绑定的真实 consumer，不得扩大 production allowlist。

禁止迁移：构造 `FetchResult` 的 `ssrf_blocked_fetch_result()`、`raise_if_fetch_url_blocked()`、
`split_fetch_urls_by_ssrf()`，以及 Provider fallback、content quality、Browser Worker 路由和任何
Fetch DTO。Rollback 是恢复 legacy implementation 和 consumer import；没有数据或配置迁移。

### 6.3 Redaction

Canonical path 为 `souwen.common_runtime.security`，repository-internal public interface 为：

```python
def scrub_secret_text(text: str | None) -> str | None: ...
def redact_secret_text(text: str | None) -> str | None: ...
def redact_secret_url(url: str | None) -> str: ...
```

Security 只拥有基于 field-name、Bearer/Authorization、quoted/scalar key-value、URL userinfo、query
和 fragment 的通用 stdlib scrubber。输入/输出保持现有 string/`None` 语义，redaction placeholder 仍为
`"***"`；safe text、path、query/fragment non-secret fields 和 URL 末尾 punctuation/bracket 必须保留。
`_is_secret_field()` 是 legacy compatibility 所需的 module-private helper，不加入 package `__all__`。

本切片无 I/O、network、global mutable state、retry、timeout 或 cooperative cancellation point；每次调用
只执行同步 regex、field-name normalization 与 `urllib.parse`。现有 parser/typing error 原样传播；不得
捕获异常后返回未脱敏原文，不记录 input、match 或 secret。迁移不调整关键词/regex、placeholder、URL
encoding、punctuation 或 invalid URL 行为。

`souwen.core.redaction` 必须 object-identical re-export 三个 public primitives 和 private field classifier。
`logging_config` 与 `plugin_manager` 使用 canonical `redact_secret_text`，证明两个真实 production
consumers。`plugin_manager` 的 payload handling 继续使用 legacy adapter，不能为追求统一 import 而把
Pydantic 引入 Security。

禁止迁移：`BaseModel.model_dump()` compatibility、`redact_secret_value()`、
`redact_secret_payload()`、`redact_secret_mapping()`、LLM gateway `base_url` topology hiding、CLI/server
response shaping 和 redacted-placeholder write validation。这些包含 third-party model 或产品/Delivery
policy，继续留在 `souwen.core.redaction` 或调用边界。Rollback 是恢复 legacy implementation 和 consumer
imports；没有数据、配置或 persisted secret migration。

### 6.4 HTTP Transport

Transport v1 若进入实施，必须先冻结：

- `single_attempt` 恰好一次，`default` 只对 connect/timeout 按现状重试；
- 401/403/429/404/5xx 的现有映射；
- cancellation 原样传播，不转成 `SourceUnavailableError`，不触发额外 retry；
- v1 无 stream API；
- `follow_redirects=True` 只用于 trusted Provider API，不替代 untrusted Fetch 的逐跳 SSRF gate；
- `source_name` config resolution 先作为 compatibility adapter，不进入 Transport 核心 contract。

## 7. 验证计划

### ACCEPT-01 required evidence

| VAL ID | Evidence |
|---|---|
| VAL-CR-001 | canonical 与 legacy path export 相同四个符号，object identity 相同 |
| VAL-CR-002 | direct env、invalid direct env、explicit file、cwd/bundle/executable/module candidates 的旧/新 fixture parity |
| VAL-CR-003 | `common_runtime/observability` AST 无 Core、Delivery、module、Provider、registry import |
| VAL-CR-004 | `doctor.py` 与 `server/app.py` 使用 canonical import；external `souwen.provenance` 保持可用 |
| VAL-CR-005 | architecture checker、import surface、provenance、doctor/server targeted tests 通过 |
| VAL-CR-006 | 全量 pytest、Ruff、generated docs、wheel surface 与 CI/V2 aggregate 通过 |
| VAL-CR-007 | canonical/legacy SSRF 三个 symbols object identity 相同；`BaseScraper` 使用 canonical import |
| VAL-CR-008 | scheme/userinfo/port/IDNA/IP/legacy numeric/fake-IP/mixed DNS/reason 与 Host/SNI fixture parity |
| VAL-CR-009 | 同步 DNS、单一 `url` interface、无 timeout/cancellation 参数和 stdlib-only AST fixture 通过 |
| VAL-CR-010 | Fetch helpers/DTO 未迁移；legacy validate monkeypatch 与 local fixture override regression 通过 |
| VAL-CR-011 | canonical/core text/URL/scrub primitives 与 private field classifier object identity 相同 |
| VAL-CR-012 | Authorization/Bearer/quoted/scalar/userinfo/query/fragment/punctuation/safe-field fixture parity |
| VAL-CR-013 | canonical redaction stdlib-only；parser failure 原样传播且不返回未脱敏 input |
| VAL-CR-014 | Pydantic payload/mapping 与 LLM topology policy 留在 legacy adapter；两名 consumers canonicalized |

未来 conditional slice 必须各自增加 old/new parity、negative dependency、cancellation 和资源清理
证据；不能仅以 import 成功作为退出门槛。

## 8. 非目标与开放项

本 LLD 不做以下决策：

- Q-004–Q-008、API validation status、probe endpoint migration；
- Fetch content policy、Provider selection、Admin auth 或 YAML revision UI；
- Provider v2 SPI、manifest location、generated client；
- Browser Worker process/deployment；
- Common Runtime 独立 service、FFI 或单独 distribution。

需要后续关闭的技术项：

1. Transport owner 与显式 config options/port；
2. OAuth 属于 Transport 还是 Security，以及 token refresh cancellation；
3. neutral concurrency namespace，替代 legacy `search` / `web` channel；
4. SSRF 同步 DNS 的 timeout/cancellation 演进；
5. rate limiter cancellation 后 lock/state conformance；
6. stable transport port 出现后再定义 fake transport/clock/testing harness。

## 9. 实施任务

| Task | Scope | Exit evidence |
|---|---|---|
| CR-01 | provenance canonical move + legacy re-export + two consumers | VAL-CR-001–006 |
| CR-02 | request context primitive | canonical context 无 ASGI dependency；旧路径 re-export；request/error/log ID parity |
| CR-03 | SSRF resolver primitive | DNS/IP/Host/SNI/redirect fixtures parity; no `FetchResult` import |
| CR-04 | generic redaction split | no Pydantic/LLM policy in primitive; secret fixtures parity |
| CR-05 | trusted Provider HTTP transport | explicit cancellation/redirect/config contract and parity |
| CR-06 | generic outbound rate limiter | cancellation/state conformance; Provider header parsing outside runtime |

CR-02–CR-06 不能因 CR-01 完成而自动视为批准；每个切片都重新执行 admission test。
