# SPEC-05：Provider SPI、Manifest 与 Conformance

**状态**：Proposed；Phase 1 owner review required（待实现）
**关联 HLD**：SouWen大重构设计文档 §8.3–8.5、§12–15、§20–21、§25–27
**关联待决策**：Q-003 已由 ADR-03 关闭；Q-005、Q-006、Q-008、Q-009（迁移批次）仍开放
**关联 ADR**：[ADR 0004 / HLD register ADR-03](./adr/0004-yaml-provider-config.md)
**依赖**：SPEC-01 Canonical DTO；SPEC-02/03/04 模块 LLD；SPEC-06 Common Runtime；SPEC-07 Auth/Permission；SPEC-08 Directory/Dependency。

## 1. Scope and fact baseline

This is the target **Provider Extension v2** contract. It does not claim that the
SPI, manifest schema, Provider Manager, or revisioned configuration workflow is
already implemented.

In scope: three narrow SPIs, Provider manifest validation, one assembly path,
lifecycle, configuration/secret boundary, failure isolation, observability, and
deterministic conformance. Out of scope: canonical DTO/API fields, search
orchestration/ranking/fallback, numeric NFRs, UI layout, package marketplace or
trust signing, and revision-store implementation.

### 1.1 Verified current state (not target claims)

| Area | Current fact | Evidence |
|---|---|---|
| Registry/source truth | Built-in sources use SourceAdapter plus MethodSpec; registry views derive catalog/default/capability projections. | src/souwen/registry/adapter.py, catalog.py, views.py, sources/ |
| Lazy loading | lazy(module:Class) delays concrete Client-class import; it does not create v2 capability instances. | src/souwen/registry/loader.py |
| Configuration | SouWenConfig carries source channels, LLM gateways and plugins; precedence is env > project YAML > user YAML > .env > defaults. | src/souwen/config/models.py, loader.py, docs/configuration.md |
| Legacy plugins | souwen.plugins entry points/config paths load Plugin, SourceAdapter, collections or factories; they can hook lifecycle, register fetch handlers, and unload at runtime. | src/souwen/plugin.py, plugin_manager.py, docs/plugin-integration-spec.md |
| Legacy manifest | docs/plugin-manifest.schema.json is optional author-side lint metadata; runtime discovery still uses Python entry points. | docs/plugin-manifest.schema.json |
| Admin control plane | Current YAML editing writes/reloads a chosen file; source config writes mutate in-memory SouWenConfig; plugin endpoints expose legacy manager. No target revision/ETag contract exists. | src/souwen/server/routes/admin/config.py, sources.py, plugins.py, schemas/admin.py |
| Existing tests | Registry/plugin/config/admin tests certify current behavior, not Provider Extension v2 conformance. | tests/registry/, tests/test_plugin*.py, tests/test_config*.py, tests/test_server/test_app.py |

### 1.2 Current-to-target mapping

| Current element | Target Provider Extension v2 mapping | Migration constraint |
|---|---|---|
| SourceAdapter/MethodSpec and registry declarations | Provider package: manifest plus one-or-more single-capability adapters. | Preserve registry/catalog facts until package v2 conformance; no parallel source list. |
| lazy Client loader | Provider Manager lazy creation after declaration/config/adapter validation. | Core cannot see concrete providers before validation. |
| registry.views / Source Catalog | Current inventory and migration input, not target Manifest Registry implementation. | Existing catalog contract remains until separately migrated. |
| Plugin, entry points, hooks, runtime unload/install | Legacy lifecycle to be replaced per Provider. | No compatibility promise or immediate removal. |
| Optional legacy plugin JSON manifest | Distinct runtime-required v2 Provider manifest. | Do not reinterpret existing schema as v2. |
| SouWenConfig plus current YAML/env loading | Target Configuration/Secret Resolver boundary. | ADR-03 defines durable YAML; field migration belongs to SPEC-06/07. |
| Existing admin YAML/source/plugin routes | Future authenticated Provider editor. | Current routes are not revision/concurrency implementations. |

## 2. Slice routing and traceability

| Requirement/source | Required slice | Reason | Priority | Blocks dev? |
|---|---|---|---|---|
| HLD §12 | PROV, MAN, CONF | Provider boundary and proof contract. | P0 | Yes |
| HLD §15.3–15.4 | SEC | Secret and supply-chain constraints. | P0 | Yes |
| HLD §8.5, §25 | VAL | Deterministic testing/observability. | P0 | Yes |
| HLD §14 | SPEC-02/03/04 | Orchestration and canonical semantics are not Provider-owned. | P1 | Per use case |
| HLD §13, Q-003 | ADR-03; SPEC-06/07 | Persistent config, authorization, secret resolution. | P0 | Yes |
| HLD §16, Q-008 | NFR SPEC; SPEC-10 | Numeric targets/release evidence remain unapproved. | P1 | Before release |

| ID family | Source | Validation | Downstream owner |
|---|---|---|---|
| PROV-* | HLD §8.3–8.4, §12.1–12.2 | CONF-*, VAL-* | Provider Manager/module LLDs |
| MAN-* | HLD §12.3–12.4, §25 | CONF-*, SEC-* | Manifest Registry/package |
| CONF-* | HLD §12.5, §21 Phase 5 | VAL-* | Testing Kit/package |
| SEC-* | HLD §15, ADR-03 | VAL-* | Common Runtime/Auth |
| VAL-* | HLD §8.5, §12.5, §25 | — | Test/observability/release owners |

Cross-document references MUST use qualified form `SPEC-05/<ID>` (for example,
`SPEC-05/SEC-001`). Unqualified `SEC-*`, `OBS-*`, and `VAL-*` in this document are
local shorthand and do not alias another SPEC's local IDs.

## 3. Provider SPI contract

### PROV-001: Ownership and dependency rule

- A Provider package MAY contain multiple adapters; every adapter MUST implement
  exactly one declared SPI.
- Core/use cases MUST depend only on SPI types and canonical DTOs, never on
  package-private provider clients, parsers, or transport objects.
- A Provider MUST NOT call another Provider. Composition, fallback, merge, and
  deduplication belong to an approved Core use case.
- SPI output MUST be canonical result/error, never an upstream SDK object.
- Construction/calls MUST accept Core-provided cancellation and execution-budget
  context. Exact signatures/fields remain SPEC-01/06 decisions.

**Acceptance**: dependency tests reject Core-to-concrete-provider imports;
fixtures show canonical output; no supported production API enables direct
cross-provider calls.

### PROV-002: SearchProvider

~~~text
SearchProvider.search(SearchRequest, RequestContext) -> SearchPage
~~~

Semantic request minimum: query, filters, cursor, limit, locale. Response
minimum: canonical results, optional next cursor, provenance. Manifest MUST
declare pagination and exposed ordering semantics; it MUST NOT invent stable
sorting. Ranking, defaults, multi-source ordering, and merge are SPEC-02/Q-004.

**Acceptance**: deterministic fixtures cover success, empty page, declared
pagination, invalid request/config, timeout/cancel, rate limit, invalid upstream
payload, and provenance.

### PROV-003: LLMSearchProvider

~~~text
LLMSearchProvider.search(LLMSearchRequest, RequestContext) -> LLMSearchResult
~~~

Semantic request minimum: query, model reference, search options, budget.
Result minimum: canonical answer, evidence, citations, usage, provenance. The
adapter performs one search-oriented upstream LLM/API call and normalizes
output/errors. It MUST NOT silently call ordinary Search, Fetch, Summarize,
rerank, or an Agent workflow. Q-005 keeps final evidence/citation/usage minima
open; harness checks preservation/shape, not an invented quality threshold.

**Acceptance**: fixtures prove no hidden cross-capability call, preserve
returned evidence/citations/usage, classify empty/unsupported safely, and map
errors canonically.

### PROV-004: FetchProvider

~~~text
FetchProvider.fetch(FetchRequest, RequestContext) -> FetchResult
~~~

Semantic request minimum: URL, content policy, budget. Result minimum:
canonical content, metadata, provenance. The adapter receives validated request
metadata and bounded policy context; this never authorizes skipping Provider- or
Worker-side SSRF/DNS/redirect controls. Proxy, WARP, browser runtime, and manifest
declaration provide no exemption. Every redirect and fallback target requires
security revalidation. Content length/type/quality are Q-006 and SPEC-04 decisions.

**Acceptance**: fake transport fixtures prove policy rejection, redirect
revalidation handoff, timeout/cancel, invalid response classification, and
provenance; browser/real-network smoke stays outside ordinary pytest.

### PROV-005: Common outcome semantics

| Outcome | Required behavior |
|---|---|
| Success | Return only capability canonical result/page and provenance. |
| Empty | Canonical empty; never mask upstream failure as success. |
| Invalid request/config | Fail before upstream call when determinable. |
| Cancelled/deadline | Stop according to context and retain canonical category. |
| Rate limited | Preserve classification and supported safe retry metadata. |
| Invalid upstream response | Classify invalid; do not coerce arbitrary content into success. |
| Policy blocked | Keep distinct from network/auth/provider availability. |

Exact error strings/fields remain SPEC-01/module-LLD owned. Providers cannot
introduce private cross-boundary error vocabularies.

## 4. Manifest contract

### MAN-001: Identity and status

A v2 Provider manifest is a versioned package-scoped declaration consumed by
the target Manifest Registry. It is distinct from the legacy optional plugin
schema and Python entry points.

- Exactly one manifest per Provider package MUST have stable unique package ID,
  schema_version, package version, and compatible contract_version
  (provider-v2).
- Final resource filename/location is an LLD/Directory decision; this SPEC does
  not invent current repository layout.
- Manifest validation precedes lazy adapter construction.
- Identity/version feed inventory/provenance and MUST NOT carry secrets or
  unbounded opaque diagnostics.

### MAN-002: Future JSON Schema minimum

The following are normative schema sections, not a claim that checked-in v2
schema already exists.

| Section | Required fields / constraints |
|---|---|
| Identity | schema_version, stable id, version, contract_version; reject incompatible/duplicate active identity. |
| Capabilities | Non-empty subset of search, llm_search, fetch; each maps to one exported adapter. |
| Adapter declarations | Package-local identity/reference, its one capability, availability constraints; never arbitrary remote code location. |
| Configuration | Versioned config-schema declaration/reference, non-secret keys, explicit unknown-key policy. |
| Secrets | Secret names/references only; no values, defaults, examples, credential-bearing URLs. |
| Network | Egress, proxy support, browser requirement, host/network declarations needed for review. |
| Risk | At least authenticated/costed flags; further taxonomy explicit/reviewable. |
| Observability | Stable safe IDs/dimensions only; no request/body/secret-bearing free text. |
| Compatibility | Supported contract/config-schema range; incompatible values fail closed. |

Final JSON Schema MUST deliberately control additionalProperties (normally
false), validate stable opaque IDs, reject duplicate capability/adapter entries,
and enumerate constrained values.

### MAN-003: Declaration/implementation agreement

Manifest Registry stores validated declarations without provider business calls.
Provider Manager MUST verify declaration/export/SPI agreement before resolving
an adapter. A multi-capability package is allowed, but one adapter is one SPI.
Manifest/adapter IDs are immutable within a loaded package generation; a config
edit changes eligibility, not topology. Malformed schema, incompatible version,
duplicate identity, export mismatch, or required-dependency failure quarantines
only that package.

**Acceptance**: negative fixtures cover required-field failures, incompatible
contracts, duplicates, forbidden extra fields, export mismatch, and one package
failure while a distinct valid Provider remains usable.

## 5. Unique assembly and lifecycle

### PROV-006: Sole assembly path

~~~text
Discover Manifest
 -> Validate manifest schema and contract version
 -> Resolve non-secret config and secret references
 -> Validate config against declared config schema
 -> Validate declared adapters against package exports/SPI
 -> Register eligible declarations in Manifest Registry
 -> Lazy-create requested adapter
 -> Execute only through its SPI
 -> Canonicalize result or error
 -> Probe (explicitly requested) / Close
~~~

No route, UI, CLI, use case, or import side effect may bypass this sequence by
directly constructing a concrete Provider. Discovery is not eligibility;
registration is not instance creation; instances are not global-singleton
contract.

### PROV-007: Lifecycle and isolation

~~~text
undiscovered -> discovered -> validated -> registered-eligible
  -> lazy-created -> active -> closing -> closed
any validation/config/dependency failure -> quarantined
active/lazy-created fatal provider-local fault -> quarantined -> closing -> closed
~~~

Discovery/validation MUST not search, fetch, bill, install arbitrary packages,
or mutate business data. probe is explicit, bounded, read-only/low-impact, and
cannot enable a Provider. close is idempotent, cancellation-aware, and releases
only owned resources. Failure records safe provider-local reason and must not
disable/unregister unrelated packages. Instance sharing/cache/reload needs
Provider Manager LLD/NFR confirmation.

### PROV-008: Legacy lifecycle separation

Current startup/shutdown hooks, health hooks, entry-point reload, runtime
install/uninstall, and plugins.state.json are legacy behavior—not v2 lifecycle.
Each migration MUST document current truth, target manifest/SPI, coexistence rule
preventing double dispatch, and rollback to known current behavior.

## 6. Configuration and security

### SEC-001: Provider config ownership

Target Configuration/Provider Manager owns configuration; provider code,
route-local mutable objects, and parallel source lists do not. ADR-03 makes YAML
the durable record. Manifest declares config shape and secret names/references,
never values. Provider receives only its resolved namespace. Bad
namespace/schema/secret reference makes that Provider ineligible with a safe
diagnostic and leaves unrelated Providers usable.

### SEC-002: Secret boundary

- No literal API key, password, cookie, bearer token, client secret, or
  credential-bearing URL may appear in target YAML, manifest, revision history,
  diff/audit payload, static Panel bundle, inventory, log, metric, exception,
  provenance, or test snapshot.
- YAML MAY contain approved secret reference/name only. Secret Resolver resolves
  it at runtime only for the needing Provider and supplies redacted diagnostics.
- Missing/inaccessible/malformed secret reference is local eligibility failure;
  it never triggers value logging or borrowing another namespace secret.

### SEC-003: Fetch and supply chain

Fetch declarations cannot relax SSRF, DNS binding, redirects, content policy,
timeouts, or redaction. Target runtime uses build-selected Provider packages and
does not install arbitrary URLs. Package/manifest/inventory provenance is safe
and readback-capable. Third-party signing/trust needs a separate ADR/SPEC.

**Acceptance**: redaction fixtures find no literal secret across serialized
views; browser/proxy remains subject to Fetch security; rejected config does not
affect a healthy Provider.

## 7. Conformance harness

### CONF-001: Modes

Every v2 package MUST pass one deterministic harness using fake transport,
clock, cancellation, fixtures, and fault injection; ordinary pytest never needs
real network, browser runtime, production secrets, paid accounts, or HOME.

| Mode | Purpose | Gate |
|---|---|---|
| Static manifest | schema/version/export/capability/prohibited fields | ordinary deterministic test |
| Config/secret | namespace isolation, failure/redaction | ordinary deterministic test |
| SPI behavior | canonical success/empty/errors/cancel | ordinary deterministic test |
| Lifecycle | lazy create, probe, idempotent close, quarantine | ordinary deterministic test |
| Functional/deployment smoke | bounded live provider/browser evidence | separate approved script/workflow |

### CONF-002: Mandatory provider cases

For every declared adapter the harness asserts:

1. manifest/config-schema compatibility and declaration/export agreement;
2. canonical success with provenance and canonical empty;
3. invalid request/config and missing/invalid secret reference without leakage;
4. timeout, cancellation, rate-limit, invalid-upstream, and policy-blocked distinction;
5. deterministic fake transport/fixtures;
6. provider-local failure isolation;
7. explicit bounded probe and idempotent cancellable close;
8. no cross-provider call or network-security bypass; and
9. safe package/adapter/manifest version diagnostics.

LLMSearchProvider additionally preserves evidence/citation/usage; FetchProvider
adds policy and redirect-revalidation handoff. Q-005/Q-006/Q-008 thresholds
remain excluded until owners close them.

### CONF-003: Failure diagnostics

Failures are attributable to package/provider/adapter/capability plus safe class.
Quarantine does not stop a valid distinct package. Authorized diagnostics may
show stable codes/redacted reasons only; raw upstream bodies, paths,
credentials, cookies, passwords, and secrets stay hidden. Harness failure blocks
that Provider migration but does not prove legacy removal or release/deployment.

## 8. Observability and validation

### OBS-001 / VAL-001: Safe events

| Event | Trigger | Required safe properties | Forbidden |
|---|---|---|---|
| provider_manifest_validated | validation ends | provider ID, package/contract version, outcome/reason | secret values/fields |
| provider_registered | declaration eligible | provider, adapter, capability | config/request body |
| provider_instance_created | lazy creation ends | provider, adapter, class, elapsed bucket | secrets/public stack trace |
| provider_call_completed | SPI call ends | provider, adapter, capability, outcome, elapsed, cancel/retry, correlation ID | query, URL content, result body, credentials |
| provider_probe_completed | probe ends | provider, adapter, status, elapsed | secret/error body |
| provider_closed | close ends | provider, adapter, outcome | raw resource detail |
| provider_quarantined | local failure | provider, adapter, reason, authorized config revision ID | secret/raw config/diff |

### OBS-002 / VAL-002: Metrics/readback

| Signal | Minimum dimensions | Purpose | Threshold owner |
|---|---|---|---|
| Call count/outcome | provider, adapter, capability, outcome | availability/error evidence | NFR SPEC |
| Latency | provider, adapter, capability, outcome | budget analysis | NFR SPEC |
| Quarantine inventory | package/provider/adapter/reason | safe diagnosis | Provider Manager/Auth |
| Active manifest inventory | package/provider version, contract, capabilities | runtime/build provenance | Deployment SPEC |
| Config revision | provider namespace/revision ID, redacted state | audit/concurrency evidence | ADR-03/SPEC-07 |

No label contains unbounded query/URL/header/exception/body/secret. Alerts,
SLOs, retention, cardinality budgets are Q-008/NFR decisions.

### Validation acceptance matrix

| ID | Acceptance criterion | Evidence |
|---|---|---|
| VAL-003 | One SPI per adapter; canonical outcomes only. | Package conformance fixtures |
| VAL-004 | Manifest/schema/version/export agreement before instantiate. | Static negative/positive fixtures |
| VAL-005 | Sole assembly path; no concrete-provider bypass. | Dependency + manager integration tests |
| VAL-006 | Config/secret failure redacted and provider-local. | Fake resolver/config tests |
| VAL-007 | Outcome classes remain distinguishable. | Deterministic SPI fixtures |
| VAL-008 | Probe safe/bounded; close idempotent/cancellable. | Lifecycle fault fixtures |
| VAL-009 | Browser/proxy does not bypass Fetch security. | Fetch fixture; live smoke separate |
| VAL-010 | Observability/inventory/diff diagnostics bounded/redacted. | Log-capture/schema tests |
| VAL-011 | Provider migration rollback has no duplicate dispatch. | Migration integration/inventory readback |

Before calling a Provider migrated, the owner supplies manifest fixtures,
relevant VAL evidence, current-to-target mapping, config/secret inventory, and
rollback note. Legacy tests alone are not v2 proof; v2 tests alone are not
release/deployment proof.

## 9. Open questions and dev handoff

| ID | Question | Closure owner |
|---|---|---|
| Q-005 | Minimum LLM evidence/citation/usage. | SPEC-01 + SPEC-03 |
| Q-006 | Fetch content length/type/quality. | SPEC-04 |
| Q-008 | Performance/concurrency/memory/image/cold-start targets. | NFR SPEC + SPEC-10 |
| Q-009 | Later Provider migration batches. | Phase 4/5 owner |
| OQ-PROV-01 | Manifest resource location/Python representation. | Provider Manager + SPEC-08 |
| OQ-PROV-02 | Canonical error/context fields. | SPEC-01 + SPEC-06 |
| OQ-PROV-03 | Third-party signing/trust workflow. | Separate security ADR/SPEC |
| OQ-PROV-04 | Instance sharing/cache/reload policy. | Provider Manager LLD + NFR |

Implementers MUST not relabel legacy plugin APIs as v2, create parallel source
lists, import-time registration, arbitrary runtime installation, secret-bearing
manifest/YAML/history, or browser/proxy security exceptions. First vertical
slice waits for SPEC-01 and SPEC-08. All open rows need owner confirmation and
must not close with implementation defaults.
