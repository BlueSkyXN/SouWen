# Phase 1：Target Canonical Contract Fixtures

**状态**：Accepted target baseline；不是 current runtime contract。

## 1. 载体与单一真源

Phase 1 以 language-neutral JSON 冻结已批准的 target contract：

| Artifact | 目的 | 不是 |
|---|---|---|
| [`target_api_contract_v2.json`](../../../tests/contracts/fixtures/target_api_contract_v2.json) | approved decision、canonical operation、golden response and budget baseline | FastAPI runtime snapshot、生产 route implementation |
| [`target_openapi_skeleton_v2.json`](../../../tests/contracts/fixtures/target_openapi_skeleton_v2.json) | target OpenAPI semantic skeleton and target probe alias policy | generated/release `openapi.json` |
| [`target_provider_manifest_v2.json`](../../../tests/contracts/fixtures/target_provider_manifest_v2.json) | v2 manifest/conformance minimum and safe negative cases | current plugin entry-point schema |
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

`implemented_by_current_runtime: false` and `x-souwen-contract-stage: target_skeleton_not_runtime` are
deliberate anti-confusion markers. They prevent a passing static fixture test from being misreported as proof that
the current FastAPI application serves target `/api/v1` operations or canonical probes.

## 3. Deterministic acceptance and next implementation gate

Run:

```bash
pytest tests/contracts/test_target_canonical_contract.py -v --tb=short
```

This verifies fixture integrity, target/current separation, accepted decision values, OpenAPI skeleton parity,
and manifest safety/conformance declarations. It does not validate production route behavior. A later target
implementation must add route/schema tests for every golden, generate immutable OpenAPI and clients from one
source, and prove the selected Provider packages through the SPEC-05 harness.
