# ADR 0005: Breaking API and Release Cutover

**HLD decision-register ID**: ADR-04

**Status**: Accepted

**Date**: 2026-07-24
**Scope**: `2.0.0` target architecture release, External Data API distribution and binary release surface

## Context

The current repository already has a `/api/v1` FastAPI surface, a Python package named `souwen`, CLI/MCP
entry points, multiple current search response shapes, current basic/pro/full editions and two binary builders.
Those current facts are not the desired product boundary:

- `src/souwen/server/app.py` mounts public routes at `/api/v1`, but current Search is mainly several GET
  resource endpoints and `POST /api/v1/search/web/enriched`; the target HLD calls for canonical `POST`
  Search, LLM Search and Fetch contracts.
- `src/souwen/server/schemas/common.py` currently defines a flat error body, while HLD §11.5 calls for a
  nested canonical error contract with stable codes and retry semantics.
- `pyproject.toml` currently exposes direct Python library/CLI dependencies and current package version
  `2.0.0rc1`; `.github/workflows/build-pyinstaller.yml` builds 3 CLI editions across 4 targets, and the
  release workflow currently verifies 24 PyInstaller/Nuitka binaries.
- HLD §20 and §27 close Q-011: the target release surface is **four cross-platform PyInstaller server
  bundles**, with Nuitka and basic/full tiers retired. HLD §20 also selects the REST Client SDK as the
  default `souwen` Python distribution direction.

The project needs one explicit decision so the same path `/api/v1` is not mistaken for backward compatibility,
old client DTOs do not silently connect to the target service, and release-workflow inheritance is not treated
as the target release contract.

## Options considered

### Option A — Keep current `/api/v1` wire behavior and add target endpoints additively

Keep current GET Search variants, enriched route, Fetch response and error format stable; add canonical routes
alongside them.

- **Advantages**: fewer immediate client migrations.
- **Rejected because**: preserves contradictory DTOs and duplicated product semantics indefinitely, does not
  realize the HLD three-use-case boundary, and lets incompatible clients appear to work.

### Option B — Publish a new `/api/v2` path while retaining `/api/v1`

Put the target canonical DTOs under a new URI major and operate both surfaces in parallel.

- **Advantages**: URI makes the break obvious and supports a long dual-run.
- **Rejected because**: HLD §11 and Q-011 explicitly select an in-place `/api/v1` cutover for `2.0.0`; running
  two public contracts expands security, test, docs, generated-client and release obligations without approved
  usage evidence for the old surface.

### Option C — In-place `/api/v1` breaking cutover with explicit API-major handshake

Replace the wire contract at `/api/v1` for `2.0.0`, version canonical schemas independently through an API
major, generate official clients from an immutable OpenAPI artifact and fail clients on a major mismatch.

- **Advantages**: one stable product contract, matches HLD, prevents accidental old/new DTO decoding and keeps
  release verification focused.
- **Costs**: released clients must migrate; release needs explicit mapping, fixtures and strong contract gates.

### Binary distribution alternatives

| Alternative | Decision | Reason |
|---|---|---|
| Keep PyInstaller + Nuitka; retain basic/pro/full matrix | Rejected | Current 24-binary matrix is release evidence for a broader, retiring CLI/edition product surface, not the target server contract. |
| Stop shipping all binaries | Rejected | Q-011 has closed on four PyInstaller server bundles. |
| Four cross-platform PyInstaller **server** bundles; retire Nuitka and basic/full tiers | Accepted | Matches HLD §20/§27 and produces a smaller, server-focused release evidence boundary. |

## Decision

1. `2.0.0` performs an **in-place breaking cutover at `/api/v1`**. A matching URI prefix is not a promise that
   current v2 RC payloads remain compatible. The target canonical operations are `POST /api/v1/search`,
   `POST /api/v1/llm-search`, `POST /api/v1/fetch` and `GET /api/v1/providers`, defined in
   [SPEC-01](../spec-01-external-api-canonical-dto.md).
2. The target wire contract has **API major 2**, independent from package/marketing version. Every server
   response and target OpenAPI document declares it; official clients must validate it before DTO decode.
   API-major mismatch is explicit and non-fallback: clients must not parse an unknown schema as untyped JSON,
   retry old paths or weaken auth/policy behavior.
3. The target OpenAPI document is a generated, versioned, immutable release artifact. The default install
   surface of the Python distribution `souwen` becomes a **REST SDK** generated from (or strictly conformant
   to) that document; Server, Worker and Provider runtimes remain selectable extras of the same distribution.
   This is not a promise that direct imports of current search/fetch internals remain the default product API.
   The TypeScript generated client uses the same document and golden fixtures.
4. The `2.0.0` binary release surface is exactly **four cross-platform PyInstaller server bundles**:
   Linux amd64, Linux arm64, macOS arm64 and Windows amd64. The target release contract retires Nuitka and
   basic/full tier artifacts. A platform bundle must contain the server runtime, canonical API and, for an
   all-in-one profile, the separately built approved Web artifact. The Web artifact does not re-enter the
   Python wheel as a source/build dependency. A bundle does not restore CLI/MCP product commitments.
5. Migration communications, usage evidence and removal residue are not waived by this ADR. They are owned by
   SPEC-11, with Q-001/Q-002 evidence retained for risk classification even though removal direction is closed.

## Consequences

### Positive

- Client/server compatibility becomes testable and observable: generated SDKs cannot quietly attach to a
  different API major.
- Search, LLM Search and Fetch can share canonical errors, provenance, RequestContext and provider boundaries.
- Release evidence shrinks from the current 24 binary combination assumption to four server artifacts, allowing
  a clear, reviewable release inventory.

### Required work and risks

- Current `/api/v1` consumers can break at cutover. Before release, SPEC-11 must publish operation/field/error
  replacement mapping, migration guide, release notes and residue audit; Q-001/Q-002 usage evidence determines
  migration risk, not whether removal is silently reversed.
- Existing current workflow files, `edition-basic`/`edition-pro`/`edition-full` extras and PyInstaller/Nuitka
  jobs are **implementation inventory**, not evidence that this ADR has already been implemented. Workflow,
  packaging, docs and validation changes require separate approved work.
- API major, package version, generated-client version and OpenAPI artifact checksum must be recorded together
  in release provenance. A green CI, matching package version or a `/api/v1` path alone is insufficient.
- In-place cutover increases the need for release sequencing: do not deploy a target server while only old
  generated clients are distributed, or distribute target clients before a compatible server is selected.

### Non-goals

- This ADR does not decide Q-004 Search ranking, Q-005 LLM evidence/usage minimum, Q-006 Fetch quality bounds,
  Q-007 Data API auth default or Q-008 performance/quotas.
- This ADR does not delete current routes, source code, binaries, CLI/MCP, generated artifacts or workflows.
- This ADR does not authorize a new API URI, backward-compatibility shim or production rollout.

## Acceptance gates

| Gate | Required proof |
|---|---|
| Canonical wire contract | Frozen target OpenAPI semantic diff and versioned golden JSON fixtures for success/validation/auth/rate-limit/provider/error flows. |
| Generated clients | Python `souwen` REST SDK and TypeScript client regenerated from the same immutable OpenAPI artifact; conformance tests pass. |
| Misconnection prevention | Matrix proves old/unsupported client major fails safely before decode/business retry and matching major succeeds. |
| Release inventory | Release manifest contains exactly four target PyInstaller server bundles, with platform-specific checksum, source SHA, API major, OpenAPI checksum and smoke result. |
| Retirement evidence | No Nuitka or basic/full tier artifact is required by the target release workflow; no replacement workflow claims their old CLI/MCP surface as target evidence. |
| Migration evidence | SPEC-11 usage/readback, replacement mapping, migration guide, RC validation and residue audit complete before final removal claim. |

## Related artifacts and evidence

- Approved HLD v0.4 §11, §20, §21 and §25–27.
- Decision/SPEC register entries Q-001–Q-011, SPEC-01 and ADR-04.
- [SPEC-01: External API and Canonical DTO](../spec-01-external-api-canonical-dto.md)
- [ADR 0001: current public API surface](0001-public-api-surface.md)
- [ADR 0002: current v2 RC release version](0002-versioning-policy.md)
- Current app/auth/error evidence: `src/souwen/server/app.py`, `src/souwen/server/auth.py`,
  `src/souwen/server/schemas/common.py`
- Current packaging/release evidence: `pyproject.toml`, `.github/workflows/build-pyinstaller.yml`,
  `.github/workflows/build-nuitka.yml`, `.github/workflows/release-candidate.yml`

## Review condition

Review only when an approved change proposes a new API major, reverses Q-011 binary policy, or evidence shows
the four-bundle server surface cannot meet approved NFR/release requirements. A review may supersede this ADR;
it must not silently add a compatibility path, retain a retired binary tier, or redefine API major semantics.
