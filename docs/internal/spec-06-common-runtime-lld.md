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
| `OAuthClient` | EPO OPS、CNIPA | **ACCEPT-07** | client-credentials acquisition/cache/bearer 属于 Transport；legacy config adapter 保持，先冻结 refresh cancellation 与 secret boundary |
| `core.concurrency` 原 API | Search、Web aggregation | **ACCEPT-08，neutral primitive only** | runtime 只接收 explicit-size loop-local pool；`"search"` / `"web"` 与 env policy 留在 legacy adapter |
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

CR-05 分成 error identity prerequisite 与 HTTP execution core 两个 stacked 单元，不能让 canonical
Transport 临时反向 import `souwen.core.exceptions`，也不能以 error factory 改变异常 identity。

#### 6.4.1 Canonical error identity

Common Runtime 拥有 project-neutral base；Transport 拥有 stable outbound failure taxonomy：

```python
# souwen.common_runtime.errors
class SouWenError(Exception): ...

# souwen.common_runtime.transport
class AuthError(SouWenError): ...
class RateLimitError(SouWenError):
    retry_after: float | None
class SourceUnavailableError(SouWenError): ...
```

`souwen.core.exceptions` 必须 object-identical re-export 上述四类；`ConfigError`、`ParseError`、
`NotFoundError` 和 `LocalCatalogUnavailableError` 保持 legacy/domain 定义。后者仍直接继承 canonical
`SourceUnavailableError`，所有 legacy broad `except SouWenError`、Provider `pytest.raises()` 和
`RateLimitError.retry_after` 保持。禁止创建同名第二套 class、catch 后翻译成新实例，或因本切片批量
改写所有 legacy consumers。

#### 6.4.2 Explicit options 与 compatibility adapter

Canonical Transport 只接收上层已经解析的 `base_url`、merged headers、timeout、proxy、
`follow_redirects` 和当前 retry setting，不读取 `SouWenConfig`、registry、credential、HOME、env 或
`souwen.__version__`。Repository-internal interface 为：

```python
RequestRetryPolicy = Literal["default", "single_attempt"]

class HttpTransport:
    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str],
        timeout: int | float,
        max_retries: int,
        proxy: str | None,
        follow_redirects: bool,
    ) -> None: ...
```

`httpx` 和 `tenacity` 是本切片明确准入的 runtime libraries；该 interface 不加入 `souwen.__init__`
end-user export。legacy `souwen.core.http_client.SouWenHttpClient` 继承 `HttpTransport` 并保留原构造
签名与 compatibility adapter，负责：

1. `get_config()` 与 `source_name` 的 base URL/proxy/header resolution；
2. User-Agent 构造；
3. header precedence：User-Agent < source channel headers < explicit caller headers；
4. 保留 current `timeout or config.timeout`、`max_retries or config.max_retries` 语义。

当前 `self.max_retries` 只保存值，实际 tenacity stop 固定为三次；CR-05 是同行为搬移，不能顺手让该
字段改变 attempt count。source timeout/backend、credential 和 Provider response body policy 不进入
Transport core。`OAuthClient` 继续继承 legacy adapter；token acquisition/cache/bearer methods 由后续
CR-07 canonical OAuth Transport 提供。

#### 6.4.3 Retry、status、cancellation 与生命周期

- `single_attempt` 恰好一次；`default` 只对 `httpx.TimeoutException` / `ConnectError` 固定三次；
- timeout/connect 分别映射 `SourceUnavailableError("请求超时")` / `("连接失败")`；
- 401/403 → `AuthError`，429 → 带 numeric/HTTP-date `retry_after` 的 `RateLimitError`，404 返回原
  response，5xx → `SourceUnavailableError`，其他 4xx → `SouWenError`；
- `asyncio.CancelledError` 原样传播，不转译、不触发额外 retry；retry backoff cancellation 同样原样传播；
- context manager 正常/异常退出都只 delegate `httpx.AsyncClient.aclose()`；v1 不新增独立 `_closed`
  state、重复 close 保证或 cancellation recovery policy；
- v1 无 stream API；不在本切片添加 tracing/metrics；
- `follow_redirects=True` 只保持 trusted Provider API 现状，不替代 untrusted Fetch/PDF 的逐跳 SSRF、
  DNS binding、Host/SNI 或跨 origin header policy；
- Provider 可以继续 override status hook，例如 YouTube 403 quota mapping；generic Transport 不读取
  Provider JSON body。

#### 6.4.4 兼容迁移与 rollback

CR-05a 先移动四类 canonical error objects，并让 legacy HTTP/retry 成为至少两个直接 consumers。
CR-05b 再建立 explicit Transport core 与 legacy config adapter；OAuth token acquisition/cache/lock/bearer
injection 全部留在后续单元。Rollback 必须能分别恢复 error definitions 和 HTTP implementation，不需要
数据、配置或 persisted credential migration。

### 6.5 Outbound Rate Limiter

Canonical path 为 `souwen.common_runtime.resilience`，repository-internal interface 保持：

```python
class RateLimiterBase(ABC):
    async def acquire(self) -> None: ...
    def update_from_headers(
        self,
        remaining: int | None = None,
        retry_after: float | None = None,
    ) -> None: ...

class TokenBucketLimiter(RateLimiterBase):
    def __init__(self, rate: float, burst: int | None = None): ...

class SlidingWindowLimiter(RateLimiterBase):
    def __init__(self, max_requests: int, window_seconds: float = 60.0): ...
```

实现只依赖 stdlib `abc`、`asyncio`、`collections.deque` 和 monotonic `time`。Token bucket 的
`burst or max(1, int(rate))`、refill/扣减顺序和持锁 sleep 保持；Sliding window 的 strict `< cutoff`、
`+0.01s` 边界、`max_requests=0` fallback、retry pause/restore 与 synchronous
`update_from_headers()` 状态更新保持。本切片不顺手新增参数校验、clock/sleep injection、跨 event-loop
共享保证或 update/acquire 原子性。

`acquire()` 不 shield cancellation。request task 在 token wait、retry pause 或 window wait 被取消时，
`async with` 必须释放 lock；已存在 token/timestamp/retry state 保持在 cancellation point 的状态，后续
调用继续按 monotonic time 恢复。接口无内部 timeout；外层 task 拥有 cancellation/budget。

`update_from_headers()` 只接收调用方已解析的 `int | None` 与 `float | None`。具体 header 名称、字符串
解析、monthly quota logging 与 `RateLimitError` 构造继续归 Provider；Common Runtime 不 import HTTP
response、config、registry 或具体 Provider。`souwen.core.rate_limiter` object-identical re-export 三类，
OpenAlex 与 The Lens 作为 token/sliding 两个 representative canonical consumers。Rollback 只恢复旧定义
与 consumer imports，无数据或 persisted state migration。

### 6.6 OAuth Client-Credentials Transport

OAuth client-credentials acquisition、in-memory token cache、refresh lock 和 Bearer injection 属于
Transport；它不定义 Provider credential source、secret persistence、Admin permission 或 config schema。
Canonical repository-internal interface 为：

```python
class OAuthTransport(HttpTransport):
    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str],
        timeout: int | float,
        max_retries: int,
        proxy: str | None,
        follow_redirects: bool,
        token_url: str,
        client_id: str,
        client_secret: str,
    ) -> None: ...
```

token endpoint 继续直接使用同一个 `httpx.AsyncClient.post()`、相同 timeout/proxy/redirect options，
不新增 token-specific retry。非 200、JSON parse failure、缺少 `access_token` 分别映射为现有
`AuthError`；HTTPX network error 与 `expires_in` 类型/算术错误仍按现状原样传播。默认 `expires_in=1200`
且在 expiry 前 60 秒刷新；恰好位于 refresh boundary 时必须刷新。

每个实例 lazy 创建一个 `asyncio.Lock`，double-check 后只允许一个 refresh 请求。request cancellation
或 lock-waiter cancellation 原样传播；`async with` 释放 lock，未完成 refresh 不写 token/expiry，其他
waiter 或后续调用可以继续。接口不 shield cancellation、不跨 event loop 共享实例、不持久化 token，
也不记录 `client_id`、`client_secret`、access token 或 response body。

Bearer header 先由 cached token 构造，再按现有行为由 caller headers 覆盖；本切片不改变该 precedence。
legacy `OAuthClient` 同时保持 `OAuthTransport` 与 `SouWenHttpClient` 子类关系，构造参数、source config
resolution、User-Agent 和 lifecycle 不变；四个 operational methods 与 canonical method object 相同。
EPO OPS 与 CNIPA 继续通过 legacy adapter 使用 canonical implementation。Rollback 恢复 legacy methods
和单继承，不需要配置、credential 或 persisted token migration。

### 6.7 Loop-Local Semaphore Pool

Common Runtime 只拥有中立的 per-event-loop semaphore state；不拥有 Search/Web channel、环境变量或
产品并发默认值。Canonical repository-internal interface 为：

```python
class LoopLocalSemaphorePool:
    def get(self, size: int) -> asyncio.Semaphore: ...
    def clear(self) -> None: ...
```

每个 pool 用 `WeakKeyDictionary[AbstractEventLoop, Semaphore]` 保存当前 running loop 的实例。同一 pool、
同一 loop 重复调用返回同一 object，首次 `size` 生效；不同 loop 或不同 pool 必须隔离。`size=0` 与负数
分别保持 `asyncio.Semaphore` 的既有允许/拒绝语义，不新增校验。协程外调用继续由
`asyncio.get_running_loop()` 抛出 `RuntimeError`。loop 无其他强引用时 weak entry 可被回收；`clear()`
丢弃该 pool 的所有 entries，不关闭 loop、不取消 task，也不修改既有 semaphore object。

`souwen.core.concurrency` 保留 `SOUWEN_MAX_CONCURRENCY`、默认值 10、非法值 fallback、`search` / `web`
channel validation、exact error 与 `clear_semaphore()` compatibility。legacy adapter 为两个 channel 各持有
一个 canonical pool，Search 和 Web aggregation 继续通过旧函数使用 canonical state，因此不改变公开
或测试 patch surface。接口无 I/O、timeout、retry 或 cancellation point；不跨 process/thread 共享。
Rollback 恢复 legacy maps；无数据、配置或 persisted state migration。

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
| VAL-CR-015 | canonical/core 四类 error object identity 与完整 legacy/domain inheritance 保持 |
| VAL-CR-016 | Common Runtime error AST 无 legacy Core、Delivery、Provider、registry 或 config import |
| VAL-CR-017 | RateLimit `retry_after`、HTTP status/network mapping 与 non-HTTP broad catch parity |
| VAL-CR-018 | config adapter 的 base URL/proxy/header/timeout precedence；core 不读 source credential/backend |
| VAL-CR-019 | single/default attempt count、native request/backoff cancellation 和 subclass hook parity |
| VAL-CR-020 | normal/exception context close delegate、无 stream v1、trusted redirect/SSRF negative boundary |
| VAL-CR-021 | canonical/legacy wheel paths、至少两个 consumers、全量 pytest、Ruff、CI/V2 通过 |
| VAL-CR-022 | 三类 limiter canonical/core object identity；完整 class semantic AST parity |
| VAL-CR-023 | canonical limiter stdlib-only；无 HTTP/config/registry/Provider import 或 header-name policy |
| VAL-CR-024 | token wait cancellation 释放 lock 并保留 pre-sleep token/refill state |
| VAL-CR-025 | retry pause/window wait cancellation 释放 lock，保留 pause/timestamp 并可由后续 acquire 恢复 |
| VAL-CR-026 | OpenAlex token + The Lens sliding consumers canonicalized；Provider 继续解析 headers |
| VAL-CR-027 | legacy limiter regression、Provider tests、wheel、全量 pytest、Ruff、CI/V2 通过 |
| VAL-CR-028 | OAuth 四个 operational methods semantic AST parity；legacy MRO/API 与 canonical method identity |
| VAL-CR-029 | canonical OAuth 无 config/Core/registry/Provider dependency；explicit options construction |
| VAL-CR-030 | cache hit、60s boundary、default expiry、single refresh 与 token error mapping parity |
| VAL-CR-031 | token-request/lock-wait cancellation 原样传播、释放 lock、不写 partial cache 且可恢复 |
| VAL-CR-032 | Bearer injection/caller override、invalid retry policy 与 HTTP execution parity |
| VAL-CR-033 | EPO OPS/CNIPA 使用 canonical methods；logs/wheel 不暴露 credential/token values |
| VAL-CR-034 | OAuth/Provider regression、全量 pytest、Ruff、architecture、wheel、CI/V2 通过 |
| VAL-CR-035 | same-loop identity、first-size-wins、different-loop 与 different-pool isolation |
| VAL-CR-036 | explicit zero/negative size、no-running-loop、clear 与 weakref cleanup 语义保持 |
| VAL-CR-037 | canonical concurrency stdlib-only；无 env、Search/Web、config、registry 或 Provider policy |
| VAL-CR-038 | legacy env/default/channel/exact-error/clear contract 与 Search/Web consumers 保持 |
| VAL-CR-039 | architecture、import、Search/Web regression、wheel、全量 pytest 与 Ruff 通过 |

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

1. SSRF 同步 DNS 的 timeout/cancellation 演进；
2. stable transport port 出现后再定义 fake transport/clock/testing harness。

## 9. 实施任务

| Task | Scope | Exit evidence |
|---|---|---|
| CR-01 | provenance canonical move + legacy re-export + two consumers | VAL-CR-001–006 |
| CR-02 | request context primitive | canonical context 无 ASGI dependency；旧路径 re-export；request/error/log ID parity |
| CR-03 | SSRF resolver primitive | DNS/IP/Host/SNI/redirect fixtures parity; no `FetchResult` import |
| CR-04 | generic redaction split | no Pydantic/LLM policy in primitive; secret fixtures parity |
| CR-05a | shared/transport error identity prerequisite | VAL-CR-015–017；legacy identity 与 inheritance parity |
| CR-05b | trusted Provider HTTP execution core | VAL-CR-018–021；explicit cancellation/redirect/config contract and parity |
| CR-06 | generic outbound rate limiter | VAL-CR-022–027；cancellation/state conformance；Provider header parsing outside runtime |
| CR-07 | OAuth client-credentials transport | VAL-CR-028–034；refresh/cache/cancellation/secret boundary parity |
| CR-08 | neutral loop-local semaphore pool | VAL-CR-035–039；domain/env policy stays in legacy adapter |

CR-02–CR-08 不能因前一切片完成而自动视为批准；每个切片都重新执行 admission test。
