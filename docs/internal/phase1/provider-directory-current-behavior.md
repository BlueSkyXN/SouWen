# Phase 1B：Provider / Directory Current-Behavior Mapping 与 Golden Fixture

**状态**：current-only baseline；不构成 Provider Extension v2、YAML revision
workflow、目录重组或业务决策。
**范围**：冻结当前 registry、SourceAdapter、MethodSpec、legacy plugin、configuration
loader，以及已观察到的目录直接依赖。
**相关目标材料**：SPEC-05、SPEC-08、ADR-03 仅作为未来目标边界；本文件不修改、
不复述为已实现，也不关闭 Q-005、Q-006、Q-008、Q-009。

## 1. Evidence and fixture boundary

Language-neutral fixture：

~~~text
tests/contracts/fixtures/provider_directory_current_v1.json
~~~

它是当前事实的最小可移植 JSON 表达，不是可执行 manifest、Provider v2
schema、runtime configuration，且不包含凭据、真实 URL、用户 HOME 或当前外部
网络状态。测试从真实 Python objects 和源码导入关系读取事实，并验证 fixture
仍与它们一致：

~~~text
tests/contracts/test_provider_directory_current_contract.py
~~~

测试刻意不跑真实 provider、browser、外部 plugin discovery 或配置文件写入；它只
验证当前静态/本地对象和 source text。实时网络、package 安装、部署和 Provider v2
conformance 不在本基线的证明范围。

## 2. Current registry / adapter facts

| Current concern | Frozen fact | Source of truth | Explicit non-claim |
|---|---|---|---|
| Source identity and dispatch metadata | SourceAdapter owns current name/domain/integration/config-field/client-loader/method mapping metadata. | src/souwen/registry/adapter.py and src/souwen/registry/sources/ | Not a v2 Provider package or capability SPI. |
| Current method mapping | MethodSpec maps a capability to a concrete Client method, parameters, optional pre-call transform, and optional attempt timeout. | src/souwen/registry/adapter.py | Not canonical request/result/error contract. |
| Registry projection | views exposes current adapter lookup/domain/capability/default/fetch projections; catalog derives public catalog data. | src/souwen/registry/views.py and catalog.py | Not a target Manifest Registry. |
| Lazy import | lazy(module:Class) resolves a Client class on demand and caches the import path. | src/souwen/registry/loader.py | Not Provider Manager lazy instance lifecycle. |
| Built-in source inventory | Tests assert stable representative current sources only; complete inventory remains source-derived and may legitimately change. | registry views at test runtime | Not a committed future migration batch. |

Current standard capability vocabulary is broader than target three SPI names:
search variants, detail/trending/transcript, fetch, and archive operations are
current registry capability declarations. A current SourceAdapter can therefore
have several method entries; this must not be read as an accepted exception to
the SPEC-05 rule that a target v2 adapter implements exactly one SPI.

The fixture locks complete current standard capability/domain enumerations because
they are constants, but uses only representative registered source IDs
(openalex and builtin) so routine catalog expansion does not invalidate a
Phase 1 baseline without a contract change.

## 3. Legacy plugin and current configuration facts

| Concern | Current fact | Future-boundary note |
|---|---|---|
| Plugin discovery | Python entry-point group is souwen.plugins. | This is legacy plugin discovery, not a Provider v2 manifest loader. |
| Entry shape | Current loader accepts Plugin, SourceAdapter, list/tuple, or a zero-argument factory returning them. | A v2 Provider package/manifest contract is not implemented by this acceptance rule. |
| Runtime mutation | External adapters can register/unregister in current registry; legacy plugins can own fetch handlers and lifecycle hooks. | It is not the target Provider Manager lifecycle or supply-chain model. |
| Configuration model | SouWenConfig currently includes sources, llm_search_gateways, plugins, and plugin_config. | Field presence does not establish a v2 provider namespace schema. |
| Precedence | Current effective precedence is environment > project YAML > user YAML > dotenv > defaults. | ADR-03 chooses one future durable Provider YAML record; current merge behavior remains current behavior. |
| Admin mutation | Current YAML route validates/reloads an atomically replaced file; source config route assigns to in-memory cfg.sources. | Neither proves target revision IDs, semantic diffs, optimistic concurrency, or rollback history. |

No test in this baseline asserts target implementation absence by scanning arbitrary
new directories. Parallel Phase 1 implementation may add target materials without
invalidating these tests. Instead, every fixture/document target note is a scope
guard: developers must not promote the current object/lifecycle semantics to a
target conformance claim.

## 4. Observed directory dependency mapping

The JSON fixture records a small set of direct import edges read from current
source text/AST. They are descriptive current facts, not allowed-dependency rules
for a new architecture.

~~~text
src/souwen/registry/views.py
  -> souwen.registry.adapter

src/souwen/registry/catalog.py
  -> souwen.registry
  -> souwen.registry.adapter

src/souwen/plugin.py
  -> souwen.registry.adapter
  -> souwen.registry.views
  -> souwen.web.fetch
~~~

These edges support the current model:

1. Registry views consume the adapter type.
2. Catalog is a projection over registry views and adapter metadata.
3. Legacy plugin code directly bridges the registry and fetch-handler runtime.

They do **not** authorize a future Core-to-concrete-provider import, a direct
Provider-to-Provider call, an import-time v2 Provider registration path, or a
new parallel source list. Those are target constraints owned by SPEC-05 and
SPEC-08.

## 5. Golden fixture test rules

The fixture/test pair must stay narrow and deterministic:

- JSON is parsed with the Python standard library and re-serialized without a
  language-specific schema/runtime.
- Registry checks import actual SourceAdapter, MethodSpec, constants, and views.
  They inspect dataclass fields, current capability/domain constants, and
  representative current registry entries.
- Plugin/config checks import actual ENTRY_POINT_GROUP, SouWenConfig, and loader
  constants; source checks confirm the current precedence merge sequence and
  current admin write/mutation markers.
- Directory checks parse Python AST and compare only fixture-listed direct import
  edges. They do not infer an entire architecture graph.
- Tests do not mutate registry, write YAML, load plugins, resolve secrets, or
  make network/browser calls.

If current behavior intentionally changes, update fixture, test, and this mapping
together with the owning current behavior tests. Do not alter the fixture merely
to make a future design appear implemented.

## 6. Residual dependencies and non-decisions

| Item | Status | Owner |
|---|---|---|
| Canonical DTO/error/context and v2 SPI signatures | Not frozen here. | SPEC-01, SPEC-02/03/04, SPEC-06 |
| v2 Provider manifest resource/schema/manager | Target-only. | SPEC-05, SPEC-08 |
| YAML revision store, secret reference grammar, auth/audit/UI editor | Target-only. | ADR-03, SPEC-06/07, UI SPEC |
| LLM evidence/usage minimum | Q-005 open. | SPEC-01/03 |
| Fetch quality/content limits | Q-006 open. | SPEC-04 |
| NFR targets | Q-008 open. | NFR SPEC |
| Full Provider migration batches | Q-009 batches open. | Phase 4/5 owner |
