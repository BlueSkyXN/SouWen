# Phase 1：Target Canonical Contract Fixtures

**状态**：Accepted target baseline；API contract 已由 rollout-gated target runtime 实现，
Provider manifest 仍是 Phase 5 待完成基线。

## 1. 载体与单一真源

Phase 1 以 language-neutral JSON 冻结已批准的 target contract：

| Artifact | 目的 | 不是 |
|---|---|---|
| [`target_api_contract_v2.json`](../../../tests/contracts/fixtures/target_api_contract_v2.json) | approved decision、canonical operation、golden response and budget baseline | generated/release `openapi.json` |
| [`target_openapi_skeleton_v2.json`](../../../tests/contracts/fixtures/target_openapi_skeleton_v2.json) | target OpenAPI semantic skeleton and target probe alias policy | generated/release `openapi.json` |
| [`target_provider_manifest_v2.json`](../../../tests/contracts/fixtures/target_provider_manifest_v2.json) | v2 manifest/conformance minimum and safe negative cases | retired plugin entry-point schema |
| [`test_target_canonical_contract.py`](../../../tests/contracts/test_target_canonical_contract.py) | standard-library deterministic invariants | target route, SDK or provider integration test |

These files live under `tests/contracts/fixtures/` only because the Phase 2 `contracts/` tree does not yet
exist. They are the sole checked-in target fixture source during Phase 1. Phase 2 must move them atomically into
the target tree (or replace them with a generated artifact plus a recorded provenance link), never maintain a
second copy. No fixture imports `souwen`, calls a route, reads HOME configuration, or makes a network request.

## 2. Approved decision closure

The owner approved `Q-004`–`Q-008`, `API-Q-001`, and `REL-Q-001`. The API fixture records the exact target
defaults: one YAML-ordered primary absent explicit providers; explicit fanout with RRF `k=60`; evidence/usage
minimum; bounded text/JSON/XML Fetch; fail-closed USER+ Data API; initial non-SLA budgets; HTTP 400 client input
errors; and `/healthz`/`/readyz` canonical probes with 2.x aliases. The detailed normative prose remains in
[SPEC-01](../spec-01-external-api-canonical-dto.md); Provider implications are in
[SPEC-05](../spec-05-provider-spi-manifest-conformance.md), and future artifact placement is governed by
[SPEC-08](../spec-08-directory-dependency.md).

P4-06 将 API fixture 更新为 `implemented_by_current_runtime: true`，并将 OpenAPI stage 更新为
`target_runtime_rollout_gated`。该声明只在 `SOUWEN_V2_ROLLOUT=target` 时覆盖 target Data API；
default `legacy` 仍保留 current route 作回滚路径。`target_provider_manifest_v2.json` 继续保持
`implemented_by_current_runtime: false`，直到 Phase 5 完成全量 Provider 处置。Static fixture 仍不是
runtime proof；runtime 语义由 `tests/test_delivery_api_v2.py` 对真实 `app.openapi()`、route、auth、
headers 和 probes 进行 deterministic 对照。

## 3. Deterministic acceptance and next implementation gate

Run:

```bash
pytest tests/contracts/test_target_canonical_contract.py -v --tb=short
```

This verifies fixture integrity, target/current separation, accepted decision values, OpenAPI skeleton parity,
and manifest safety/conformance declarations. P4-06 route/schema behavior is validated separately by
`tests/test_delivery_api_v2.py`. Phase 6 must still generate an immutable OpenAPI artifact and clients from one
source; Phase 5 must prove every selected Provider package through the SPEC-05 harness.
